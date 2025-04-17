#!/bin/python

import time
import uuid
import os
import sys
import signal
import argparse
import logging
import datetime
import asyncio
import threading
import subprocess
import functools
import shlex
import base64
from tempfile import mkstemp

from zmsclient.zmc.client import ZmsZmcClient
from zmsclient.dst.client import ZmsDstClient
from zmsclient.zmc.v1.models import Subscription, EventFilter
from zmsclient.dst.v1.models import Observation
from zmsclient.common.subscription import ZmsSubscriptionCallback

# Boston's monitor.
MONITOR     = "/usr/bin/rfmonitor";
# For observation upload.
CURL        = "/usr/bin/curl";
# Only when a daemon
LOGFILE     = "/local/logs/rdz-monitor.log"

# Global logger
LOG = None

# Not sure where to pick these up
EVENT_TYPE_REPLACED    =     1
EVENT_TYPE_CREATED     =     2
EVENT_SOURCETYPE_ZMC   =     2
EVENT_CODE_GRANT       =     2006

#
# Heartbeat task
# 1) Signal we are alive. Duh.
# 2) Advertise what can be configured.
# 3) What else?
#
class HeartBeat:
    def __init__(self):
        self.state = "running"
        self.done  = False
        pass
    
    async def start(self):
        while not self.done:
            print("HeartBeat sleeping")
            await asyncio.sleep(5)
            print("HeartBeat done sleeping")
            pass
        print("Heartbeat task is exiting")
        pass

    def stop(self):
        print("HeartBeat stopping")
        self.done = True
        pass

    pass

#
# Monitor thread. Run the monitor in a thread, looping until told to stop.
#
class Monitor:
    def __init__(self, monitor_id, description, dstclient, zmcclient,
                 frange=None, gain=None, interval=0):
        self.monitor_id  = monitor_id
        self.description = description
        self.dstclient   = dstclient
        self.zmcclient   = zmcclient
        self.monitor_id  = monitor_id
        self.range       = frange
        self.gain        = gain
        self.interval    = interval
        self.event       = threading.Event()

        #
        # Must map outer monitor to inner monitor for rdzinrdz.
        # This test is bogus.
        #
        # This will raise an exception if it fails
        #
        if zmcclient._base_url.find("rdz.powderwireless.net") < 0:
            self.mapOuterMonitor();
            pass
        pass

    def run(self):
        command = MONITOR + " -o -n -g " + str(self.gain) + " "
        command = command + "-R " + self.range
        LOG.debug(command)

        while not self.event.is_set():
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
                self.child = None
                self.upload(fname)

                #
                # We do not want to blocking sleep for a long time since then
                # we might end up waiting for a long time to reconfig.
                #
                if self.interval:
                    count = self.interval
                    while count > 0:
                        time.sleep(1)
                        if self.event.is_set():
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
        self.runstate  = "stopped"
        self.task      = None
        self.done      = False
        pass

    async def start(self):
        LOG.info("ZMCSubscriptionCallback start")
        self.startMonitor()
        await self.run_callbacks()
        pass

    def on_event(self, ws, evt, message):
        if evt.header.source_type != EVENT_SOURCETYPE_ZMC:
            LOG.error("on_event: unexpected source type: %r (%r)",
                      evt.header.source_type, message)
            return

        # Since we are subscribed to all ZMC events for this element,
        # there will be chatter we do not care about.
        if (evt.header.code != EVENT_CODE_GRANT):
            return

        try:
            self.handleEvent(evt.object_)
        except Exception as ex:
            LOG.exception(ex)
            pass
        pass

    def stop(self):
        LOG.info("ZMCSubscriptionCallback stop")
        self.done = True
        if self.task:
            self.monitor.event.set()
            self.task = None
            self.runstate = "stopped"
            pass
        pass

    def handleEvent(self, object):
        LOG.info("event: %r", object)
        pass
    
    def startMonitor(self):
        LOG.info("startMonitor")
        self.monitor.event.clear()
        self.thread = asyncio.to_thread(self.monitor.run)
        self.task = asyncio.create_task(self.thread)
        self.runstate = "running"
        pass

    async def stopMonitor(self):
        LOG.info("stopMonitor")
        if self.task:
            self.monitor.event.set()
            await self.task
            LOG.info("Monitor has stopped")
            self.task = None
            self.runstate = "stopped"
            pass
        pass

    pass


# The hander has to be outside the async main.
def set_signal_handler(signum, task_to_cancel):
    def handler(_signum, _frame):
        asyncio.get_running_loop().call_soon_threadsafe(task_to_cancel.cancel)
    signal.signal(signum, handler)
    pass

def init_main():
    parser = argparse.ArgumentParser(
        prog="rdz-monitor",
        description="Run the monitor and report results to the RDZ")
    parser.add_argument(
        "-d", "--debug", default=0, action="count",
        help="Increase debug level: defaults to INFO; add once for zmsclient DEBUG; "+
        "add twice to set the root logger level to DEBUG")
    parser.add_argument(
        "-b", "--daemon", default=False, action="store_true",
        help="Daemonize")
    parser.add_argument(
        "--logfile", default=LOGFILE, type=str,
        help="Redirect logging to a file when daemonizing.")
    parser.add_argument(
        "--gain", default=20, type=int)
    parser.add_argument(
        "--range", type=str, required=True)
    parser.add_argument(
        "--interval", type=int, default=0, required=False)
    parser.add_argument(
        "--monitor-id", type=str, required=True)
    parser.add_argument(
        "--monitor-description", type=str, required=True)
    parser.add_argument(
        "--element-token", type=str, required=True,
        help="Element token")
    parser.add_argument(
        "--zmc-http", type=str, required=True,
        help="ZMC URL")
    parser.add_argument(
        "--dst-http", type=str, required=True,
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

    dstclient = ZmsDstClient(args.dst_http, args.element_token,
                             detailed=False, raise_on_unexpected_status=True)
    zmcclient = ZmsZmcClient(args.zmc_http, args.element_token,
                             detailed=False, raise_on_unexpected_status=True)

    monitor   = Monitor(args.monitor_id, args.monitor_description,
                        dstclient, zmcclient,
                        frange=args.range, gain=args.gain, interval=args.interval)
    
    ZMCsubscription = ZMCSubscriptionCallback(
        zmcclient, monitor,
        subscription=Subscription(
            id=str(uuid.uuid4()), filters=[]),
        reconnect_on_error=True)

    heartbeat = HeartBeat()

    return ZMCsubscription, heartbeat, args.daemon, args.logfile
    pass

def ask_exit(signame, loop):
    LOG.info("got signal %s: exit" % signame)
    loop.stop()    

async def async_main(*args):
    if False:
        this_task = asyncio.current_task();
        set_signal_handler(signal.SIGINT, this_task)
        set_signal_handler(signal.SIGHUP, this_task)
        set_signal_handler(signal.SIGTERM, this_task)
    else:
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
            sub.stop()
            pass
        raise
    pass

def main():
    ZMCsubscription, heartbeat, daemonize, logfile = init_main()
    format = "%(levelname)s:%(asctime)s: %(message)s"

    if daemonize:
        try:
            fp = open(logfile, "a");
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

    subs = [ZMCsubscription, heartbeat]
    asyncio.run(async_main(*subs))
    exit(0);

if __name__ == "__main__":
    main()
