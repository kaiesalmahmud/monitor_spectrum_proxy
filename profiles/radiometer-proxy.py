"""Allocate a radio and run the RDZ monitor.
"""

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg
import geni.rspec.igext as ig
# Import the emulab extensions library.
import geni.rspec.emulab
import profiles.allRadios as radios

#
# Setup the Tour info. We will add instructions below.
#  
tour = ig.Tour()
tour.Description(ig.Tour.TEXT, "Allocate all radios and run the monitor");

#
# Defaults for this setup
#
IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-GR310"
MS        = "urn:publicid:IDN+emulab.net+authority+cm"
INSTALL   = "/local/repository/install.sh"
INSTALLZMS= "/local/repository/install-zmsclient.sh"
COMMAND   = "sudo /local/repository/rdz-monitor.py --daemon  "
PROBE     = "/local/repository/probe.pl  "

# kaies - dynamic range
try:
    with open("/local/repository/freq_range.txt", "r") as f:
        RANGE = f.read().strip()
except:
    RANGE = "3350e6-3750e6"  # Fallback default


INTERVAL  = 10

# Default gains by RadioType.
defaultGains = {
    "B210" : 52,
    "X310" : 15,
}
# The Select list provides index into above dict.
radioSelect = []
for key in radios.allRadios:
    radioSelect.append((key, key))
def cmp_key_helper(x):
    if x[0][0].islower():
        return x[0].upper()
    else:
        return x[0].lower()
radioSelect = sorted(radioSelect, key=cmp_key_helper)

# Create a portal context.
pc = portal.Context()

# Create a Request object to start building the RSpec. 
request = pc.makeRequestRSpec()

# Request a set of radios. We will default to all.
pc.defineParameter("Radios", "Radio",
                   portal.ParameterType.STRING, [], radioSelect,
                   min=0, multiValue=1, itemDefaultValue=radioSelect[0][0],
                   longDescription="Select one or more radios on which to run the monitor.")

# Loop interval
pc.defineParameter("Interval", "Loop Interval",
                   portal.ParameterType.INTEGER, INTERVAL,
                   longDescription="Loop interval, defaults to 10 seconds " +
                   "if you leave this blank.")

# Range to monitor
pc.defineParameter("Range", "Initial Frequency Range",
                   portal.ParameterType.STRING, RANGE,
                   longDescription="Initial requency range to scan. If you leave "+
                   "blank, defaults to " + RANGE + ".")

# DST Endpoint
pc.defineParameter("ZMC", "OpenZMS ZMC URL",
                   portal.ParameterType.STRING,
                   "https://rdz.powderwireless.net:8010/v1",
                   longDescription="OpenZMS ZMC URL")

# DST Endpoint
pc.defineParameter("DST", "OpenZMS DST URL",
                   portal.ParameterType.STRING,
                   "https://rdz.powderwireless.net:8020/v1",
                   longDescription="OpenZMS DST URL")

# Auth Token
pc.defineParameter("Token", "OpenZMS Token",
                   portal.ParameterType.STRING, "rpp_replaceme",
                   longDescription="OpenZMS authorization token")

# Optional install only
pc.defineParameter("NoRun", "Install Only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Install but do not run the monitor.")

# Retrieve the values the user specifies during instantiation.
params = pc.bindParameters()

# Check parameter validity.
if params.Interval != "" and params.Interval < 0:
    pc.reportError(portal.ParameterError(
    "Interval must be a non-negative integer", ["Interval"]))
    pass

if params.ZMC == "":
    pc.reportError(portal.ParameterError(
    "Must provide a ZMC URL", ["ZMC"]))
    pass
    
if params.DST == "":
    pc.reportError(portal.ParameterError(
    "Must provide a DST URL", ["DST"]))
    pass

if params.Token == "":
    pc.reportError(portal.ParameterError(
    "Must provide a OpenZMS authorization token", ["Token"]))
    pass

print("Using dynamic RANGE:", RANGE)  # kaies - print range

if params.Range != "":
    tokens = params.Range.split("-")
    if len(tokens) != 2:
        pc.reportError(portal.ParameterError(
            "Invalid Range", ["Range"]))
        pass
    pass
    
pc.verifyParameters()

#
# Set up the common part of the command
#
if params.Interval != "":
    COMMAND += " --interval " + str(params.Interval)
    pass
COMMAND += " --dst-http " + params.DST
COMMAND += " --zmc-http " + params.ZMC
COMMAND += " --element-token " + params.Token
if params.Range != "":
    tokens = params.Range.split("-")
    COMMAND += " --min_freq " + str(tokens[0])
    COMMAND += " --max_freq " + str(tokens[1])
    pass

count = 0
for radioname in params.Radios:
    radioInfo = radios.allRadios[radioname]
    radioType = radioInfo["type"]
    radioURN  = radioInfo["urn"]
    radioNode = radioInfo["node"]
    radioMonID= radioInfo["monid"]
    radioGain = defaultGains[radioType];
    command   = COMMAND
    probe     = PROBE

    if radioType == "B210":
        id = radioNode
        # FEs are special names.
        if radioNode != radioname:
            id = (radioname.split(" "))[0] + "-" + id
            pass
        node = request.RawPC(id)
        node.component_id         = radioNode
        node.component_manager_id = radioURN
        node.disk_image           = IMAGE
        probe += " B210"
    else:
        # Node
        node = request.RawPC(radioNode + '-host')
        node.hardware_type = "powder-compute"
        node.disk_image           = IMAGE
        node.component_manager_id = radioURN

        radio = request.RawPC(radioNode)
        radio.component_id         = radioNode
        radio.component_manager_id = radioURN
    
        # Link between X310 and host -- second interface
        xiface1 = radio.addInterface("xif1")
        xiface1.component_id = "eth1"
        xiface1.addAddress(pg.IPv4Address("192.168.40.2", "255.255.255.0"))
        hiface1 = node.addInterface("hif1")
        hiface1.addAddress(pg.IPv4Address("192.168.40.1", "255.255.255.0"))

        link = request.Link("link-" + str(count))
        link.addInterface(xiface1)
        link.addInterface(hiface1)
        link.bandwidth = 10 * 1000 * 1000 # 10Gbps
        link.setNoBandwidthShaping();
        link.setJumboFrames()
        count = count + 1
        probe += " X310 " + radioNode
        pass

    command += " --monitor-id '" + radioMonID + "'"
    command += " --gain " + str(radioGain)
    command += " --monitor-description '" + radioname + "'"

    node.addService(pg.Execute(shell="sh", command=INSTALL))
    node.addService(pg.Execute(shell="sh", command=INSTALLZMS))
    if not params.NoRun:
        node.addService(pg.Execute(shell="sh", command=probe))
        node.addService(pg.Execute(shell="sh", command="nohup python3 /local/repository/server.py > /local/logs/server.log 2>&1 &"))  # kaies
        node.addService(pg.Execute(shell="sh", command=command))
        pass
    pass

request.addTour(tour)

# Final rspec.
pc.printRequestRSpec(request)
