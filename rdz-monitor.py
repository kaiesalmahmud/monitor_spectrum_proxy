#!/bin/python

# Note from Kaies:
# Override range with data from the monitor

import time
import uuid
import os
import sys
import signal
import traceback
import argparse
import logging
import datetime
import asyncio
import threading
import subprocess
import functools
import shlex
import base64
import copy
import httpx
from tempfile import mkstemp

#
# Note from David
#
# * If you do monitor state update --status active , being an admin, the
#   returned MonitorState.Status will be immediately set to active and zmc
#   will generate a MonitorPending created event telling your monitor to
#   "go active"; your monitor must push monitor state update --op-status
#   active
#
# * If you do monitor state update --op-status active as the monitor token
#   from the monitor, you will be "self-activating" and the returned
#   MonitorState.Status will be active .  In this case, you will not get a
#   MonitorPending create event, because we look for this case where you have
#   just set opstatus to active, so nothing needs to be done.
#
# * If you do monitor pending create --status active the
#   MonitorState.Status will be left untouched until the monitor responds to
#   the MonitorPending event with a MonitorStateUpdate API call, setting
#   opstatus as commanded, and referencing the last_pending_id.
#

from zmsclient.zmc.client import ZmsZmcClient
from zmsclient.dst.client import ZmsDstClient
from zmsclient.zmc.v1.models import Subscription, EventFilter, Error, AnyObject
from zmsclient.dst.v1.models import Observation
from zmsclient.common.subscription import ZmsSubscriptionCallback
from zmsclient.zmc.v1.models.monitor_pending import MonitorPending
from zmsclient.zmc.v1.models.monitor_state import MonitorState
from zmsclient.zmc.v1.models.monitor_op_status import MonitorOpStatus
from zmsclient.zmc.v1.models.update_monitor_state_op_status import UpdateMonitorStateOpStatus

# Boston's monitor.
MONITOR     = "/usr/bin/rfmonitor";
# For observation upload.
CURL        = "/usr/bin/curl";
# Only when a daemon
LOGFILE     = "/local/logs/rdz-monitor.log"

# Global logger
LOG = None

# Not sure where to pick these up
EVENT_TYPE_CREATED    = 2
EVENT_SOURCETYPE_ZMC  = 2
EVENT_CODE_MONITOR_PENDING = 2010

#
# Heartbeat task
# 1) Signal we are alive. Duh.
# 2) Advertise what can be configured.
# 3) What else?
#
class HeartBeat:
    def __init__(self, monitor):
        self.monitor = monitor
        self.done    = False
        pass
    
    async def start(self):
        LOG.info("Heartbeat starting")
        try:
            await self.monitor.updateOpStatus()
        except Exception as exc:
            LOG.exception(exc)
            return;
        
        while not self.done:
            #
            # Count down till when the next heartbeat needs to go.
            # Simple for now, maybe a timeout later.
            #
            ackby    = self.monitor.state.status_ack_by
            now      = datetime.datetime.now(datetime.timezone.utc)
            duration = ackby - now
            seconds  = duration.total_seconds()

            LOG.debug("Heartbeat %r %r %r %r", ackby, now, duration, seconds)

            if seconds > 60:
                seconds = seconds - 45
                LOG.info("Heartbeat sleeping for %r seconds", seconds)
                while seconds > 0:
                    await asyncio.sleep(2)
                    if self.done:
                        break
                    seconds -= 2
                    pass
                LOG.info("Heartbeat done sleeping")
                pass
            
            if self.done:
                break;

            await self.monitor.updateOpStatus()
            LOG.info("Heartbeat next ackby is %r",
                     self.monitor.state.status_ack_by)
            pass
        LOG.info("Heartbeat task is exiting")
        pass

    async def stop(self):
        LOG.info("HeartBeat stopping")
        self.done = True
        # Fix this.
        await asyncio.sleep(3)
        pass

    pass

#
# Monitor thread. Run the monitor, looping until told to stop.
#
class Monitor:
    def __init__(self, monitor_id, description, dstclient, zmcclient,
                 dynamic=True,
                 min_freq=0, max_freq=6000, gain=10, interval=10):
        self.monitor_id  = monitor_id
        self.state       = None
        self.status      = None
        self.pending_id  = None
        self.description = description
        self.dstclient   = dstclient
        self.zmcclient   = zmcclient
        self.min_freq    = min_freq
        self.max_freq    = max_freq
        self.gain        = gain
        self.interval    = interval
        self.dynamic     = dynamic
        self.lock        = asyncio.Lock()
        self._stop       = False

        #
        # Must map outer monitor to inner monitor for rdzinrdz.
        # This test is bogus.
        #
        # This will raise an exception if it fails
        #
        if zmcclient and zmcclient._base_url.find("rdz.powderwireless.net") < 0:
            self.mapOuterMonitor();
            pass

        #
        # In dynamic mode we need our current state from ZMC.
        #
        if dynamic:
            # This will throw an error
            self.getState()
            #
            # When starting up, if the status is not active or paused,
            # then we force active. In other words, only "paused" means
            # the monitor should not send observations. 
            #
            if self.status != "paused" and self.status != "active":
                self.status = "active"
                pass
        else:
            # Not dynamic, always start up.
            self.status = "active";
            pass
        
        pass

    # Update parameters from an any_object. Yuck
    def updateParamsFromAnyObject(self, parameters):
        params = parameters.to_dict()
        for param in ["min_freq", "max_freq", "gain", "interval"]:
            if param in params:
                setattr(self, param, params[param])
                pass
            pass
        pass

    def run(self):
        self._stop = False

        while not self._stop:

            # kaies - dynamic range
            try:
                with open("/local/repository/freq_range.txt", "r") as f:
                    RANGE = f.read().strip()
            except:
                RANGE = "3350e6-3750e6"  # Fallback default

            # The monitor takes a min_freq-max_freq range argument.
            range   = str(self.min_freq) + "-" + str(self.max_freq)
            command = MONITOR + " -o -n -g " + str(self.gain) + " "
            command = command + "-R " + range
            LOG.info(command)

            LOG.info("Monitor doing something")
            #
            # Have to redirect the data to a file since UHD pollutes
            # stdout stream with stuff.
            #
            fd,fname = mkstemp()

            try:
                self.child = subprocess.Popen(
                    shlex.split(command + " -f " + fname),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE);
                if not self.child:
                    LOG.error("Popen failed: $command");
                    return
                
                # Give the process time to start.
                time.sleep(1)
                if self.child.poll() != None:
                    LOG.error("Could not start monitor process")
                    LOG.error(self.child.stderr.read(None))
                    self.child.wait()
                    self.child = None
                    return

                # We capture and process the rfmonitor output here
                # for debugging.
                output = ""
                while True:
                    line = self.child.stdout.readline()
                    if not line:
                        break
                    output = output + line.decode()
                    pass
                LOG.debug("Monitor is done")
                self.child.wait()
                if self.child.returncode == 0:
                    self.upload(fname)
                    pass
                self.child = None
                
                if self._stop:
                    break

                #
                # We do not want to blocking sleep for a long time since then
                # we might end up waiting for a long time to reconfig.
                #
                if self.interval:
                    count = self.interval
                    while count > 0:
                        time.sleep(1)
                        if self._stop:
                            break
                        count -= 1
                        pass
                    pass
                pass
            except Exception as ex:
                LOG.error("Monitor Exception")
                LOG.exception(ex)
                break
            finally:
                if fname:
                    os.remove(fname)
                    pass
            pass
        LOG.info("Monitor task is exiting")
        pass

    async def stop(self):
        self._stop = True
        if self.child:
            self.child.terminate()
            pass
        pass
    
    #
    # Construct the observation and send it up.
    #
    def upload(self, fname):
        min_freq = None
        max_freq = None
        header   = "frequency,power";

        LOG.info("Monitor reading from " + fname)
        
        with open(fname, "r") as f:
            centered = False;
            
            #
            # First line tells us what is included (center_freq is optional).
            # Also get the min_freq from the first line.
            #
            line = f.readline().rstrip()
            tokens = line.split(",")
            min_freq = float(tokens[2])
            
            if len(tokens) >= 5:
                header += ",center_freq"
                centered = True
                pass

            data = header + "\n"
            if centered:
                data += "%s,%s,%s\n" % (tokens[2],tokens[3],tokens[4])
            else:
                data += "%s,%s\n" % (tokens[2],tokens[3])
                pass

            for line in f:
                line = line.rstrip()
                tokens = line.split(",")

                if centered:
                    data += "%s,%s,%s\n" % (tokens[2],tokens[3],tokens[4])
                else:
                    data += "%s,%s\n" % (tokens[2],tokens[3])
                    pass
                pass
    
            max_freq = float(tokens[2])
            pass

        observation = Observation(
            monitor_id  = self.monitor_id,
	    description = self.description,
	    types       = "ota,sweep",
	    format_     = "psd-csv-ota",
	    min_freq    = int(min_freq * 1000000),
	    max_freq    = int(max_freq * 1000000),
            starts_at   = datetime.datetime.now(datetime.timezone.utc),
        )
        #print(str(observation))
        # After print
        observation.data = base64.b64encode(data.encode("ascii")).decode()

        LOG.info("Monitor pushing observation.data")
        response = self.dstclient.create_observation(body=observation)
        if not response:
            LOG.info("Could not create new observation")
            pass
        LOG.debug(response)
        pass

    #
    # When reporting to an RDZinRDZ, we have to map the outer monitor ID to
    # an inner monitor ID for the report.
    #
    def mapOuterMonitor(self):
        LOG.info("Mapping outer monitor ID to inner ID")
        
        inner = self.zmcclient.list_monitors(monitor=self.monitor_id)
        if not inner or not inner.monitors or len(inner.monitors) == 0:
            raise Exception("Could not map outer monitor to inner monitor")

        mon = inner.monitors[0]
        LOG.info("Mapped to inner monitor: %r", mon.id)
        self.monitor_id = mon.id
        pass

    #
    # Ask the ZNC for our state object.
    #
    def getState(self):
        monitor = self.zmcclient.get_monitor(self.monitor_id, elaborate=True)
        if not monitor:
            raise Exception("Could not get the monitor object from the ZMC")

        #
        # David says:
        #
        # If Monitor.Pending is not null and
        #    Monitor.Pending.Id != Monitor.State.LastPendingId,
        #  set your Parameters to be Monitor.Pending.Parameters, and then
        #  heartbeat that you applied that PendingId.
        #
        # Or, if Monitor.Pending is null, just make sure to initialize your
        #  Parameters from Monitor.State.Parameters -- and make sure to pause
        #  immediately if Monitor.State.Status is paused instead of going active
        #
        # This is the basis for the first heartbeat.
        #
        self.state = monitor.state

        if (not monitor.pending or
            monitor.pending.id == monitor.state.last_pending_id):

            # At the moment the params can be null, in which case better have
            # reasonable command line arguments.
            if monitor.state.parameters:
                self.updateParamsFromAnyObject(monitor.state.parameters)
                pass
            self.status = self.state.status
            if monitor.pending and monitor.pending.id == monitor.state.last_pending_id:
                self.pending_id = monitor.pending.id
                pass
            return

        # At the moment the params can be null, in which case better have
        # reasonable command line arguments.
        if monitor.pending.parameters:
            self.updateParamsFromAnyObject(monitor.pending.parameters)
            pass
        self.status = monitor.pending.status
        self.pending_id = monitor.pending.id
        pass
    
    async def updateOpStatus(self):
        LOG.info("Monitor UpdateOpStatus")
        
        await self.lock.acquire()

        # Too bad the generated api code could deal with plain strings.
        op_status = self.status
        if type(op_status) == str:
            op_status = MonitorOpStatus(op_status)
            pass
        
        opstatus = UpdateMonitorStateOpStatus(
            op_status = op_status,
            parameters = AnyObject.from_dict(
                src_dict={
                    "min_freq" : int(self.min_freq),
                    "max_freq" : int(self.max_freq),
                    "interval" : self.interval,
                    "gain"     : self.gain,
                })
        )
        # Are we responding to Pending.
        if self.pending_id:
            opstatus.last_pending_id = self.pending_id;
            self.pending_id = None
            pass

        LOG.info("Monitor UpdateOpStatus: %r", opstatus)
        
        state = self.zmcclient.update_monitor_state_op_status(
            monitor_id=self.monitor_id, body=opstatus)
        
        #LOG.info("Monitor UpdateOpStatus result: %r", state)
        
        if not state:
            raise Exception("Could not update monitor state")
        if isinstance(state, Error):
            raise Exception("Error updating the monitor: " + str(state))

        self.state = state
        self.lock.release()
        pass

    pass

#
# Command task, Takes orders from the RDZ via events. 
# 1) Change the gain.
# 2) Change the frequency range
# 3) Change ...
#
class ZMCSubscriptionCallback(ZmsSubscriptionCallback):
    def __init__(self, zmcclient, monitor, **kwargs):
        super(ZMCSubscriptionCallback, self).__init__(zmcclient, **kwargs)
        self.zmcclient = zmcclient
        self.monitor   = monitor
        self.task      = None
        self.done      = False
        pass

    async def start(self):
        LOG.info("ZMCSubscriptionCallback start:current status: %r",
                 self.monitor.status)
        if self.monitor.status == "active":
            self.startMonitor()
            pass
        LOG.info("ZMCSubscriptionCallback calling run_callbacks")
        await self.run_callbacks()

    async def on_event(self, ws, evt, message):
        if evt.header.source_type != EVENT_SOURCETYPE_ZMC:
            LOG.error("on_event: unexpected source type: %r (%r)",
                      evt.header.source_type, message)
            return

        #LOG.info("on_event: %r", evt)

        # Since we are subscribed to all ZMC events for this element,
        # there will be chatter we do not care about.
        if evt.header.code != EVENT_CODE_MONITOR_PENDING:
            return

        try:
            await self.handleEvent(evt.object_)
        except Exception as ex:
            LOG.exception(ex)
            pass
        pass

    async def stop(self):
        LOG.info("ZMCSubscriptionCallback stop")
        self.done = True
        await self.monitor.stop()
        pass

    async def handleEvent(self, pending):
        LOG.info("handleEvent: %r", pending)

        #
        # Hmm, does it make sense to change parameters when pausing? 
        #
        if pending.status != "active":
            await self.monitor.lock.acquire()
            await self.stopMonitor()
            self.monitor.pending_id = pending.id
            self.monitor.status = pending.status
            self.monitor.lock.release()
            await self.monitor.updateOpStatus();
            if pending.status != "paused":
                sys.exit(2)
                pass
            return

        #
        # Have to watch for changes to the parameters;
        #
        restart = False
        if pending.parameters:
            for param in ["min_freq", "max_freq", "gain", "interval"]:
                if (param in pending.parameters and
                    getattr(self.monitor, param) != pending.parameters[param]):
                    restart = True
                    pass
                pass
            pass

        #
        # If already active and no restart needed, then ack and done.
        #
        if self.monitor.status == "active" and restart == False:
            # No need to lock here for this one change.
            self.monitor.pending_id = pending.id
            await self.monitor.updateOpStatus();
            return

        # Parameters changed, need to stop and restart
        if self.monitor.status == "active" and restart:
            await self.stopMonitor()
            pass
        
        #
        # Lock out the heartbeat while making the changes.
        #
        await self.monitor.lock.acquire()
        if pending.parameters:
            self.monitor.updateParamsFromAnyObject(pending.parameters)
            pass

        # Start the monitor with new params
        self.startMonitor()
        self.monitor.pending_id = pending.id
        self.monitor.status = pending.status
        self.monitor.lock.release()
        await self.monitor.updateOpStatus()
        pass
    
    def startMonitor(self):
        LOG.info("startMonitor: current status: %r", self.monitor.status)
        if not self.task:
            self.thread = asyncio.to_thread(self.monitor.run)
            self.task = asyncio.create_task(self.thread)
            pass
        pass

    async def stopMonitor(self):
        LOG.info("stopMonitor: current status: %r", self.monitor.status)
        if self.task:
            self.monitor.stop()
            await self.task
            LOG.info("Monitor has stopped")
            self.task = None
            pass
        pass

    pass

def ask_exit(signame, loop):
    LOG.info("got signal %s: exit" % signame)
    loop.stop()    

async def async_main(*args):
    loop = asyncio.get_running_loop()
        
    for signame in {'SIGINT', 'SIGTERM', 'SIGHUP'}:
        loop.add_signal_handler(
            getattr(signal, signame),
            functools.partial(ask_exit, signame, loop))
        pass
    pass

    try:
        runnable = [sub.start() for sub in args]            
        await asyncio.gather(*runnable)
    except asyncio.CancelledError:
        for sub in args:
            await sub.stop()
            pass
        raise
    pass

def main():
    parser = argparse.ArgumentParser(
        prog="rdz-monitor",
        description="Run the monitor and report results to the RDZ")
    parser.add_argument(
        "-d", "--debug", default=0, action="count",
        help="Increase debug level: defaults to INFO; add once for zmsclient DEBUG; "+
        "add twice to set the root logger level to DEBUG")
    parser.add_argument(
        "--daemon", default=False, action="store_true",
        help="Daemonize")
    parser.add_argument(
        "--logfile", default=LOGFILE, type=str,
        help="Redirect logging to a file when daemonizing.")
    parser.add_argument(
        "--no-dynamic", default=False, action="store_true")
    parser.add_argument(
        "--gain", default=20, type=int)
    parser.add_argument(
        "--min_freq", type=float, required=True)
    parser.add_argument(
        "--max_freq", type=float, required=True)
    parser.add_argument(
        "--interval", type=int, default=10, required=False)
    parser.add_argument(
        "--monitor-id", type=str, required=False)
    parser.add_argument(
        "--monitor-description", type=str, required=False)
    parser.add_argument(
        "--element-token", type=str, required=False,
        help="Element token")
    parser.add_argument(
        "--zmc-http", type=str, required=False,
        help="ZMC URL")
    parser.add_argument(
        "--dst-http", type=str, required=False,
        help="DST URL")

    args = parser.parse_args(sys.argv[1:])

    global LOG
    LOG = logging.getLogger(__name__)    
    if args.debug:
        LOG.setLevel(logging.DEBUG)
        logging.getLogger('zmsclient').setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)
        logging.getLogger('zmsclient').setLevel(logging.INFO)
    if args.debug > 1:
        logging.getLogger().setLevel(logging.DEBUG)

    dstclient = None
    if args.dst_http:
        dstclient = ZmsDstClient(args.dst_http, args.element_token,
                                 detailed=False, raise_on_unexpected_status=True,
                                 httpx_args={"transport" : httpx.HTTPTransport(retries=3)})

    zmcclient = None
    if args.zmc_http:
        zmcclient = ZmsZmcClient(args.zmc_http, args.element_token,
                                 detailed=False, raise_on_unexpected_status=True,
                                 httpx_args={"transport" : httpx.HTTPTransport(retries=3)})

    monitor   = Monitor(args.monitor_id, args.monitor_description,
                        dstclient, zmcclient, dynamic=not args.no_dynamic,
                        min_freq=args.min_freq, max_freq=args.max_freq,
                        gain=args.gain, interval=args.interval)

    ZMCsubscription = None
    if not args.no_dynamic:
        ZMCsubscription = ZMCSubscriptionCallback(
            zmcclient, monitor,
            subscription=Subscription(
                id=str(uuid.uuid4()), filters=[]),
            reconnect_on_error=True)
        pass
    
    format = "%(levelname)s:%(asctime)s: %(message)s"
    if args.daemon:
        try:
            fp = open(args.logfile, "a");
            sys.stdout = fp
            sys.stderr = fp
            sys.stdin.close();
            logging.basicConfig(stream=fp, format=format)
            pass
        except:
            print("Could not open log file for append")
            sys.exit(1);
            pass
        pid = os.fork()
        if pid:
            sys.exit(0)
        os.setsid();
    else:
        logging.basicConfig(format=format)
        pass

    if args.no_dynamic:
        exit(monitor.run())
        pass

    subs = [ZMCsubscription, HeartBeat(monitor)]
    asyncio.run(async_main(*subs))
    exit(0)

if __name__ == "__main__":
    main()
