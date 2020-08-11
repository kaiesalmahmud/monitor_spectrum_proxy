from __future__ import division
import pickle,os,time
import numpy as np
from . import signal_utils as su
from . import time_utils as tu
from . import constants as C
from . import receiver
from . import device
from ..logs import logs
from ..calibration import calibration_measurements

# ------------ temp ---------------------------
# In FA_MODE, calibration is omitted and only RX1 == TX
FA_MODE = True
CAL_MAT_FA = np.array([[1,0], [0,1]])


# ------------ temp ---------------------------
# In raw mode, the max of RX1 and RX2 per frequency bin will be returned
# This is for debugging purposes only!
RAW_MODE=False
LOGS_DIR="/tmp/tx_cal_logs/" # TODO move receiver shouldn't know about where logs are
# -----------------------------------------------


# TODO:
# - I should split the data collection and post processing into two threads
# -- 1 thread for sampling data and saving it to a queue
# -- 1 thread for pulling from the queue and processing it (probably much faster, but later not)

class IsoReceiver(receiver.Receiver):
    """
    """
    def __init__(self, device_configuration, calibration_file, args):
        # TODO receiver shouldn't be setting up logger
        self.logs = logs.Logs(log_directory=LOGS_DIR)
        self.debug = args.debug
        self.print_and_log("[RECV] created log file at {}".format(LOGS_DIR))
        self.dev_config = device_configuration

        self.num_rows = C.N_BINS_TOTAL
        self.print_and_log("[RECV] Receiver N bins total {} (number of rows in messsage)".format(self.num_rows))

        try:
            self.cal_measurements = self._load_cal_data(calibration_file)
        except IOError:
            try: 
                self.cal_measurements = self._load_cal_data(C.CAL_DATA_REF)
            except IOError:
                print("[RECV] ERROR - could not load the calibration data. Using a ones matrix")
                FA_MODE=True
                self.cal_measurements = None

        self.print_and_log("[RECEIVER] Saving measurements for {} frequencies over {} steps".format(self.num_rows, C.NUM_STEPS))
        self.print_and_log("[RECEIVER] resolution: {:.2f} kHz".format(C.RES_HZ/1e3)) 

        # set up the radio device
        if "channels" in self.dev_config:
            self.devs =  self.dev_config["devices"]
            self.channels = self.dev_config["channels"]
        else:
            self.channels = C.CHANNELS

            # pull devs from dev_config 
            self.devs = []
            for k in self.dev_config:
                for frontend in self.dev_config[k]:
                    self.devs.append(str(k) + ":" + str(frontend))
            pass
        
        self.gain = args.gain
        self.rate = C.MAX_INST_BW
        self.radio_dev = device.Device(gain=self.gain, rate=self.rate,channels=self.channels)        

    def set_gain(self, gain_val):
        """ Set the gain in the receiving device
        """
        return self.radio_dev.set_gain(gain_val)

    def get_full_spectrum(self, method="welch"):
        """ See Receiver.get_full_spectrum
        """
        devs = np.array([])
        times = np.array([])
        spectrums = np.array([])
        labels = np.array([])

        

        # loop over each device in the configuration file and collect the full spectrum
        for dev in self.devs:
            
            if method=="welch":
                spectrum_i, labels_i, times_i, devs_i = self._get_psd_welch(dev)
            else:
                # collect samples, run iso algorithm and compute the PSD over all 6 GHz
                samples,cfs,times_i,devs_i = self._get_spectrum(dev)
                spectrum_i, labels_i = self._process_samples(samples,cfs)
            
            # Save results
            devs = np.append(devs, devs_i)
            times = np.append(times, times_i)
            spectrums = np.append(spectrums, spectrum_i)
            labels = np.append(labels, labels_i)
            
        return devs, times, labels, spectrums


    def get_samples(self, frequency, num_samples):
        """ See Receiver.get_samples
        """
        return self.radio_dev.get_N_samples(int(frequency), int(num_samples))


    def reconfigure_receiver(self, gain, channels):
        """ See Receiver.reconfigure_receiver
        """
        self.channels = channels
        self.gain = gain


    def _set_rf_port(self, rf_port):
        # TODO when alex has board ready, set this
        pass
     
    
    def _get_psd_welch(self, rf_port):
        """ Collect PSD
         combines _get_spectrum and _process_samples """
        # configure the port that the monitor will watch
        self._set_rf_port(rf_port)
    
        # all_samples is a 2D array with dimensions:
        # rows: number of steps (214) - with overlap total coverage takes more than previous (193)
        # columns: I/Q (2)
        # blocks: FFT length (512)
        #import pdb; pdb.set_trace()
        PSD_X_Y = np.empty((C.NUM_STEPS, 2, C.N), dtype=np.float32) 
        freq_matrix_full = np.empty((C.NUM_STEPS, C.N), dtype=np.float32)
        center_freqs = C.CENTER_FREQS
        devs = np.array([])
        times = np.array([], dtype=int)   
        
        for ii, center_freq in enumerate(center_freqs):
            N_time=C.ISO_K*C.FFT_SIZE
            samples = self.radio_dev.get_N_samples(center_freq, N_time)
            psd,labels = su.psd_welch(C.FFT_SIZE, samples, center_freq, C.N_REMOVE, self.rate)
            PSD_X_Y[ii,:, :] = psd 
            freq_matrix_full[ii,:] = labels[0,:]

            # extend devs, times to match the number of lines found per iteration.
            trep = np.tile(int(time.time()), C.N_BINS_OUT_PER_STEP) # TODO adjust time
            devrep = np.tile(rf_port, C.N_BINS_OUT_PER_STEP)
            times = np.append(times, trep)
            devs = np.append(devs, devrep)
            if ii % 20 == 0:
                self.print_and_log("[RECEIVER] spectrum collection {:.1f}% complete".format(float(ii)/C.NUM_STEPS*100))
        
        # init matrix of output PSD values
        psd_x_matrix_full = np.empty((C.NUM_STEPS, C.N))

        for ii, center_freq in enumerate(center_freqs):
            
            # run iso (samples[0,:] => RX1) # TODO add device
            if RAW_MODE:
                X,Y =  PSD_X_Y[ii, 0,:], PSD_X_Y[ii, 1,:]
            else: 
                X,Y = su.iso(CAL_MAT_FA, PSD_X_Y[ii, 0,:], PSD_X_Y[ii, 1,:])
        
            # append to freq_bins
            psd_x_matrix_full[ii, :] = X
            
        
        self.print_and_log("[RECEIVER] process samples complete")

        # final processing
        labels_MHz = freq_matrix_full / 1e6
        spectrum_out = np.ravel(psd_x_matrix_full)
        labels_MHz_out = np.ravel(labels_MHz)
        return spectrum_out, labels_MHz_out, times, devs      

    def _get_spectrum(self, rf_port):
        """ Collect spectrum """
        # configure the port that the monitor will watch
        self._set_rf_port(rf_port)
    
        # all_samples is a 2D array with dimensions:
        # rows: number of steps (214) - with overlap total coverage takes more than previous (193)
        # columns: I/Q (2)
        # blocks: FFT length (512)
        #import pdb; pdb.set_trace()
        all_samples = np.empty((C.NUM_STEPS, 2, C.FFT_SIZE), dtype=np.complex64) # DFT -> needs fft_size instead of N
        center_freqs = C.CENTER_FREQS
        devs = np.array([])
        times = np.array([], dtype=int)   
        
        for ii, center_freq in enumerate(center_freqs):
            N=C.ISO_K*C.FFT_SIZE
            samples = self.get_N_samples(center_freq, N)
            psd,labels = su.psd_welch(N, samples, center_frequency, C.N_REMOVE, self.rate)
            #dft_samples = self.radio_dev.get_dft_avg(int(center_freq),N,C.ISO_K )
            all_samples[ii,:, :] = dft_samples 

            # extend devs, times to match the number of lines found per iteration.
            trep = np.tile(int(time.time()), C.N_BINS_OUT_PER_STEP) # TODO adjust time
            devrep = np.tile(rf_port, C.N_BINS_OUT_PER_STEP)
            times = np.append(times, trep)
            devs = np.append(devs, devrep)
            if ii % 20 == 0:
                self.print_and_log("[RECEIVER] spectrum collection {:.1f}% complete".format(float(ii)/C.NUM_STEPS*100))
        
        return all_samples, center_freqs, times, devs

    def _process_samples(self, dft_samples, center_freqs):
        """Take two channels of RF samples and return the estimated spectrum of the transmitter
        """
        # init matrix of output PSD values
        psd_matrix_full = np.empty((C.NUM_STEPS, C.N))
        freq_matrix_full = np.empty((C.NUM_STEPS, C.N))

        
        for ii, center_freq in enumerate(center_freqs):
            
            # run iso (samples[0,:] => RX1) # TODO add device
            if RAW_MODE:
                X,Y =  dft_samples[ii, 0,:], dft_samples[ii, 1,:]
            elif FA_MODE:
                Y,X = su.iso(CAL_MAT_FA, dft_samples[ii, 0,:], dft_samples[ii, 1,:])
            else:
                Y,X = su.iso(self.cal_measurements.get_matrix(0, ii), dft_samples[ii, 0,:], dft_samples[ii, 1,:])

            # compute psd
            #bins = su.psd(C.FFT_SIZE, X[0:C.FFT_SIZE])
            #bins, labels = su.dft_to_psd(C.FFT_SIZE, X[0:C.FFT_SIZE], center_freqs[ii], 
            #                            n_remove=C.N_REMOVE, Fs=C.MAX_INST_BW)

            # append to freq_bins
            psd_matrix_full[ii, :] = bins
            # shift the frequency labels back based on the center frequency
            freq_matrix_full[ii, :] = labels
        
        self.print_and_log("[RECEIVER] process samples complete")

        # final processing
        labels_MHz = freq_matrix_full / 1e6
        spectrum_out = np.ravel(psd_matrix_full)
        labels_MHz_out = np.ravel(labels_MHz)
        return spectrum_out, labels_MHz_out 
    
    
    def __get_spectrum_process_test__(self, freq):
        import matplotlib.pyplot as plt
    
        # all_samples is a 2D array with dimensions:
        # rows: number of steps (1)
        # columns: I/Q (2)
        # blocks: FFT length (512)
        all_samples = np.empty((1, 2, C.FFT_SIZE), dtype=np.complex64) # DFT -> needs fft_size instead of N
        for i in range(1000):
            dft_samples = self.radio_dev.get_dft(int(freq))
        all_samples[0,:, :] = dft_samples
        
        psd_matrix_full = np.empty((1, C.N))
        freq_matrix_full = np.empty((1, C.N))
            
        if RAW_MODE:
            X,Y =  all_samples[0, 0,:], all_samples[0, 1,:]  
        elif FA_MODE:
            Y,X = su.iso(CAL_MAT_FA, all_samples[0, 0,:], all_samples[0, 1,:])
        else:
            Y,X = su.iso(self.cal_measurements.get_matrix(0, 0), all_samples[0, 0,:], all_samples[0, 1,:])

        plt.plot(range(X.shape[0]), np.real(X),range(Y.shape[0]), np.real(Y))
        plt.title("X,Y for cf {}".format(freq/1e6))
        plt.show()

        bins, labels = su.dft_to_psd(C.FFT_SIZE, X, freq, 
                                    n_remove=C.N_REMOVE, Fs=self.rate)

        psd_matrix_full[0, :] = bins
        freq_matrix_full[0, :] = labels
        labels_MHz = freq_matrix_full / 1e6
        spectrum_out = np.ravel(psd_matrix_full)
        labels_MHz_out = np.ravel(labels_MHz)

        plt.plot(labels_MHz_out, spectrum_out)
        plt.title("labels,bins for cf {}".format(freq/1e6))
        plt.show()

  
    def _load_cal_data(self, fname):
        """Load the isolation matrices for each frequency band
        """
        try:
            with open(fname, "rb") as f:
                cal_measurements = pickle.load(f)
                
        except IOError as e:
            print("[RECEIVER] Didn't load CAL data. File {} not found. Using default coefficients".format(C.CAL_DATA_FNAME))
            print("[RECEIVER] " +  e.strerror)
            
        return cal_measurements


    def print_and_log(self, message):
        """ TODO should be in logging?
        """
        if self.debug:
            self.logs.log_other(message)
            print(message)
            pass



