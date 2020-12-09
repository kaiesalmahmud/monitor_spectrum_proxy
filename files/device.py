#!/usr/bin/env python

import numpy as np
import time
from . import signal_utils as su
from . import constants as C
import os,sys
import uhd


# TODO add a method to play back already collected data (no need for real radio)

# == DEFAULTS == #
# FC32 - float (float), complex 32 -> host data format
# SC16 - integer (int16_t), complex 16 -> USRP DSP data format (auto conversion happens in the streamer)
STREAM_ARGS = uhd.libpyuhd.usrp.stream_args("fc32", "sc16")

# delay before rx to allow for time sync
INIT_DELAY = 0.05 

# indicates the number of times we will allow recv to return zero samples before restarting the stream
ZERO_RX_SAMP_THRESHOLD = 50

# Notes on stream commands:
# * `stream_now = True` for multiple channels on a single streamer will fail to time align! 
# * too many consecutive stream_cmd calls may cause the device to lock up

class Device():
    """
    Device represents a B210 USRP SDR device that can collect RF samples. 
    This class holds device-specific implementations that are irrelevant to the more abstract Receiver class

    Parameters:

    * gain - gain of the device in dB
    
    * rate - sample rate
    
    * channels - default (0,1) indicates simultaneous receive on two RX channels
    
    * num_samps_req - default number of samples collected when get_samples() is called
    
    * is_bs - True if this is a base station TODO remove reference to this -- it probably shouldn't know what a BS is
    
    * RXA - indicates the port to receive on for channel A
    
    * RXB - indicates the port to receive on for channel A
    
    * recv_frame_size - The size of the USB receive buffer in bytes - 8176 is the default maximum for USB 3.0 on a B210
    
    * num_recv_frames - The number of buffers used to store received USB transport frames


    """
    
    def __init__(self, gain=C.GAIN, rate=C.MAX_INST_BW,
                 channels=C.CHANNELS, 
                 num_samps_req=C.FFT_SIZE,
                 is_bs=False, RXA="TX/RX", RXB="TX/RX",
                 recv_frame_size=8176, num_recv_frames=50,
                 antennas=["TX/RX", "TX/RX"]):
        self.gain = gain
        self.rate = rate
        self.chans = channels
        self.antennas = antennas
        self.num_samps_req = num_samps_req
        self.is_bs = is_bs

        self.device_args  = "recv_frame_size=" + str(recv_frame_size)
        self.device_args += ",num_recv_frames=" + str(num_recv_frames)
        if is_bs:
            self.device_args += ",master_clock_rate=184.32e6"
            pass
        print("[DEVICE] device args: " + self.device_args)
        
        # setup USRP radio device
        self.usrp = uhd.usrp.MultiUSRP(self.device_args) 
        
        # set up time and frequency ref signals based on available sources
        try:
            if is_bs:
                self.usrp.set_clock_source("internal")
                self.usrp.set_time_source("internal")
                print("[DEVICE] using external reference source")
            else:
                self.usrp.set_clock_source("gpsdo")
                self.usrp.set_time_source("gpsdo")
                print("[DEVICE] using GPSDO reference source")
        except:
            self.usrp.set_clock_source("internal")
            self.usrp.set_clock_source("internal")
            print("[DEVICE] using internal reference source")

        # set to a default value to initialize the radio
        for chan in self.chans:
            self.usrp.set_rx_rate(rate, chan)
            self.usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(2400e6), chan)
            self.usrp.set_rx_gain(gain, chan)

            self.usrp.set_rx_antenna(antennas[chan], chan)
        
            # Analog band width is not properly set when using two channels currently (likely a UHD bug)
            # reduce the analog bandwidth to ~90% of the sample rate. See radio/constants.py for more details.
            self.usrp.set_rx_bandwidth(C.ANALOG_BW, 0)
            self.usrp.set_rx_bandwidth(C.ANALOG_BW, 1)
            pass
    
        # initial set up of data streamer
        self.stream_args = STREAM_ARGS
        self.stream_args.channels = self.chans
        self.streamer = self.usrp.get_rx_stream(self.stream_args)
        self.dev_buffer_size = self.streamer.get_max_num_samps() # B210, USB3.0 with default buffer size -> 2040 samples per call to recv
    
        # The garbage buffer holds data immediately collected after a re-tune.
        # data here isn't trusted so we just throw it away
        self.garbage_buffer = np.empty((len(self.chans), self.dev_buffer_size), dtype=np.complex64)

        # this buffer holds all of the samples of interest
        self.default_result = np.empty((len(self.chans), num_samps_req), dtype=np.complex64) 
        
        # synchronize channels
        # TODO update this after getting GPSDO installed. Sync to GPS clock if possible
        self.usrp.set_time_unknown_pps(uhd.types.TimeSpec(0.0))
        #gps_time = self.get_gps_time()
        #self.usrp.set_time_next_pps(uhd.uhd.types.TimeSpec(gps_time+1))

        # create start stream command
        stream_cmd = self._get_stream_start_cmd()
        self.streamer.issue_stream_cmd(stream_cmd)

        # report the configured parameters
        print("[DEVICE] Actual gain: {}".format(self.usrp.get_rx_gain(0)))
        print("[DEVICE] Actual rate: {:.2f} MSps".format(self.usrp.get_rx_rate(0)/1e6))
        print("[DEVICE] Analog bandwidth set to {:.2f} MHz".format(self.usrp.get_rx_bandwidth()/1e6))
        print("[DEVICE] Keeping {} samples from FFT size {} ".format(C.N, C.FFT_SIZE))
        print("[DEVICE] Antennas configured: ", end='')

        for channel in channels:
            antenna = antennas[channel]
            print("RF{}:{} ".format(channel, antenna), end='')
            pass
        print("")
        print("[DEVICE] USRP radio initialized successfully")        
        
        # handling tunes
        self.times = []
        self.end_collect_time = 0
        self.end_tune_time = 0

        # 50 packets (usually 2040*50=102000 samples or a millisecond worth of data (3.3ms)) typical time for a re-tune
        self.default_drop = 50*self.dev_buffer_size
        self.drops = []

        return

    def set_antennas(self, channels):
        self.stop_stream()
        self.drain_stream()
        for channel in channels:
            antenna = channels[channel];

            self.usrp.set_rx_antenna(antenna, int(channel))
            pass
        self.start_stream()
        time.sleep(1)
        print("[DEVICE] Antennas (re)configured: ", end='')
        for channel in channels:
            antenna = channels[channel];
            print("RF{}:{} ".format(channel, antenna), end='')
        print("")
        return

    def get_samples(self, frequency):
        """ use the initial number of samples as default
        """
        return self.get_N_samples(frequency, self.num_samps_req),0


    def get_N_samples(self, frequency, N):
        """ Default method
        """
        N = int(N)
        # tune to the indicated center frequency
        for chan in self.chans:
            self.usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(frequency), chan)
        
        self.end_tune_time = time.time()

        # data in the buffer is invalid (we didn't stop streaming during the re-tune), so empty
        # this could be avoided if the frequency didn't change. (TODO)
        recvd = 0
        rx_metadata = uhd.types.RXMetadata()
        received_zero_samples_x_times_in_a_row = 0
        prev_num_rx_samps = 0

        # drop packets that are invalid due to re-tune. Number of samples are proportional to re-tune time
        #import pdb; pdb.set_trace()
        tdiff = self.end_tune_time-self.end_collect_time
        #if tdiff > 0 and tdiff < 1:
        #    self.times.append(tdiff)
        num_samples_to_drop = self.rate * (tdiff) 
        if num_samples_to_drop < 0 or num_samples_to_drop > self.rate: 
            num_samples_to_drop = self.default_drop
        #self.drops.append(num_samples_to_drop)

        while recvd < (num_samples_to_drop):
            num_recvd = self.streamer.recv(self.garbage_buffer, rx_metadata)
            recvd += num_recvd

            # catch hang condition where no samples are received
            if num_recvd == 0 and prev_num_rx_samps == 0: 
                received_zero_samples_x_times_in_a_row += 1
            elif num_recvd == 0 and prev_num_rx_samps != 0:
                received_zero_samples_x_times_in_a_row = 1
            if received_zero_samples_x_times_in_a_row >= ZERO_RX_SAMP_THRESHOLD:
                print("[DEVICE] received zero samples {} times in a row. Restarting the stream".format(received_zero_samples_x_times_in_a_row))
                received_zero_samples_x_times_in_a_row = 0
                self.restart_stream()
            # sometimes we timeout and need to restart an idle radio core
            if rx_metadata.error_code == uhd.types.RXMetadataErrorCode.late: 
                print("[DEVICE] received a LATE error code. Restarting stream")
                self.restart_stream()

        # now that buffers are cleared, collect actual data
        num_accum_samps = 0
        result = np.empty((len(self.chans), N), dtype=np.complex64)
        recv_buffer = np.empty((len(self.chans), self.dev_buffer_size), dtype=np.complex64)
        
        received_zero_samples_x_times_in_a_row = 0
        prev_num_rx_samps = 0

        while num_accum_samps < N:
            # copy from internal buffer to local recv buffer
            num_rx_samps = self.streamer.recv(recv_buffer, rx_metadata)

            # catch hang condition where no samples are received
            if num_rx_samps == 0 and prev_num_rx_samps == 0: 
                received_zero_samples_x_times_in_a_row += 1
            elif num_rx_samps == 0 and prev_num_rx_samps != 0:
                received_zero_samples_x_times_in_a_row = 1
            if received_zero_samples_x_times_in_a_row >= ZERO_RX_SAMP_THRESHOLD:
                print("[DEVICE] received zero samples {} times in a row. Restarting the stream".format(received_zero_samples_x_times_in_a_row))
                received_zero_samples_x_times_in_a_row = 0
                self.restart_stream()
            # sometimes we timeout and need to restart an idle radio core
            if rx_metadata.error_code == uhd.types.RXMetadataErrorCode.late:
                print("[DEVICE] received a LATE error code. Restarting stream")
                self.restart_stream()

            # if we received > 0 samples, store them to the result array        
            if num_rx_samps:
                real_samps = min(N - num_accum_samps, num_rx_samps)
                result[:, num_accum_samps:num_accum_samps + real_samps] = recv_buffer[:, 0:real_samps]
            num_accum_samps += num_rx_samps

            prev_num_rx_samps = num_rx_samps

        self.end_collect_time = time.time()
        #
        # Ug, a lot of code just assumes two channels, so if there is
        # just a a single channel, duplicate it. Terrible! But this
        # code is millions of miles above my understanding (read: zip).
        #
        if len(self.chans) == 1:
            result = np.array([result[0], result[0].copy()])
            pass
        return result

    def get_dft_avg(self, center_frequency, N, avg_factor):
        """ N samples will be collected and split into avg_factor segments. 
        A DFT will be computed for each segment and then averaged over segments. 
        """

        if N % avg_factor != 0:
            raise Exception("avg_factor should divide N. Try increasing N. N:{}, avg_factor:{}".format(N,avg_factor))

        samples_two_chans = self.get_N_samples(center_frequency, N)
        samples_chan0 = samples_two_chans[0,:] # dim:[1,N]
        samples_chan1 = samples_two_chans[1,:] # dim:[1,N]
        
        # reshape samples from each channel to an appropriate matrix
        # Nrows = avg_factor (one for each segment)
        # Mcols = number of samples per segment
        M = N // avg_factor
        samples_chan0_reshape = np.reshape(samples_chan0,(avg_factor, M))
        samples_chan1_reshape = np.reshape(samples_chan1,(avg_factor, M))

        dft_chan0 = su.dft_mat(nfft=M, samples_mat=samples_chan0_reshape) 
        dft_chan1 = su.dft_mat(nfft=M, samples_mat=samples_chan1_reshape)
         
        dft_avg_chan0 = su.mean_complex(dft_chan0)
        dft_avg_chan1 = su.mean_complex(dft_chan1)

        # return to having two channel-vectors stacked into one matrix
        dft = np.vstack((dft_avg_chan0, dft_avg_chan1))
        return dft


    def get_dft(self, center_frequency, N=C.FFT_SIZE):
        """ Note that dft just receives the samples and computes the discrete-time fourier transform
        There is no meaningful interpretation of the numbers yet. 

        PSD representations will adjust for the analog bandwidth and center frequency.
        
        """
        return self.get_dft_avg(center_frequency, N,1) # 1 => not averaged

    def get_spectrum(self, center_frequency, N=C.FFT_SIZE, est_method='welch', avg=10):
        """ Like get_samples but directly returns the PSD instead
        """
        N_time = N*avg
        if est_method == "bartlett":
            dft = self.get_dft_avg(center_frequency, N_time, avg)
            psd,labels = su.dft_to_psd_2_chan(N, dft, center_frequency, C.N_REMOVE, self.rate)
            return psd, labels    
        elif est_method == "welch":
            samples = self.get_N_samples(center_frequency, N_time)
            psd,labels = su.psd_welch(N, samples, center_frequency, C.N_REMOVE, self.rate)
        else:
            raise Exception("[DEVICE] parameter error: psd estimation method {} not supported.".format(est_method))
        return psd, labels

    def _get_stream_start_cmd(self):
        """ Create a start stream cmd based on the current time
        """
        #self.usrp.set_time_unknown_pps(uhd.types.TimeSpec(0.0))
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        # TODO test this 
        #stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_more) # indicate that we want N samples plus more later
        # TODO test this
        stream_cmd.stream_now = False
        stream_cmd.time_spec = uhd.types.TimeSpec(self.usrp.get_time_now().get_real_secs()+INIT_DELAY)
        return stream_cmd

    def stop_stream(self):
        """ Sends a stop command to the FPGA. Subsequent calls to recv will return 0 bytes.
        """
        stream_stop_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
        self.streamer.issue_stream_cmd(stream_stop_cmd)

    def start_stream(self):
        """ Sends a start command to the FPGA.
        """
        start_cmd = self._get_stream_start_cmd()
        self.streamer.issue_stream_cmd(start_cmd)

    def drain_stream(self):
        rx_metadata = uhd.types.RXMetadata()
        count = 0
        
        while True:
            cc = self.streamer.recv(self.garbage_buffer, rx_metadata)
            count = count + cc
            if cc == 0 or rx_metadata.end_of_burst:
                break;
            pass
        print("drain_stream: ", end='');
        print(count);
        return

    def restart_stream(self):
        """ Stops, then restarts streaming on the FPGA

        # TODO: test calling recv until timeout occurs. Should empty internal buffers.
        """
        self.stop_stream()
        self._recreate_streamer()
        start_cmd = self._get_stream_start_cmd()
        self.streamer.issue_stream_cmd(start_cmd)

    def _recreate_streamer(self):
        """ using the default stream args, re-create the streamer
        This should force a clear of the buffer
        """
        self.streamer = self.usrp.get_rx_stream(self.stream_args)
        

    def get_center_freq(self):
        """ Return the center frequency (where we are currently tuned to)
        """
        return self.usrp.get_rx_freq(0)
    
    def get_sample_rate(self):
        """returns the actual sample rate"""
        return self.usrp.get_rx_rate()

    def get_gain(self):
        """returns the actual receiver gain"""
        return self.usrp.get_rx_gain()

    def set_gain(self, gain_val):
        """ Set the gain of the receiver. Return the actual value
        """
        self.usrp.set_rx_gain(gain_val)
        return self.get_gain()

    def get_num_samps_requested(self):
        """returns the configured number of samples to return"""
        return self.num_samps_req
    
    def get_serial_number(self):
        """ Returns the serial number of the USRP device"""
        info = self.usrp.get_usrp_rx_info()
        return info['mboard_serial']

    def get_temperature(self):
        """ Return the temperature of the device in degrees celsius"""
        return self.usrp.get_rx_sensor('temp').to_real()

    def get_rssi(self):
        """ Return the received signal strength indicator (RSSI) value in dB"""
        return self.usrp.get_rx_sensor('rssi').to_real()

    def get_LO_locked(self):
        """ Return the status of the lock of the local oscillator (LO)"""
        return self.usrp.get_rx_sensor('lo_locked').to_bool()
    
    def get_samples_single_chan(self, frequency, channel):
        """ This method is provided by the UHD API but only works with one channel"""
        samples = self.usrp.recv_num_samps(NUM_SAMPS_REQ, frequency, RATE, (channel,), GAIN)
        return samples

    def is_clock_internal(self):
        src = self.usrp.get_clock_source(0)
        return src == "internal"


   





    
        
 
