"""Allocate a radio and run the monitor.
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
tour.Description(ig.Tour.TEXT, "Allocate a radio and run the monitor.");

IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-GRE310"
ENDPOINT  = "urn:publicid:IDN+cpg.powderwireless.net+authority+cm"
MS        = "urn:publicid:IDN+emulab.net+authority+cm"
COMMAND   = "/local/repository/monitor.pl"

#
# Two types of situations; B210 directly connected, and X310 ethernet connected.
#
radioTypes = [
    ('B210', 'B210'),
    ('X310', 'X310'),
]
# For X310s only.
computeTypes = [
    ('Any', 'Any'),
    ('d740', 'd740'),
    ('d430', 'd430'),
    ('d820', 'd820'),
]
# Default gains by RadioType.
defaultGains = {
    "B210" : 60,
    "X310" : 15,
}
# The Select list provides index into above dict.
radioSelect = []
for key in radios.allRadios:
    radioSelect.append((key, key))
    pass

# Create a portal context.
pc = portal.Context()

# Create a Request object to start building the RSpec. 
request = pc.makeRequestRSpec()

pc.defineParameter("Radio", "Radio",
                   portal.ParameterType.STRING, radioSelect[0], radioSelect)

pc.defineParameter("ComputeType", "Compute Type",
                   portal.ParameterType.STRING, computeTypes[0], computeTypes,
                   longDescription="Select a type for X310 compute host. " +
                   "Defaults to the powder-compute soft type")

# Number of loops to run.
pc.defineParameter("runCount", "Run Count", portal.ParameterType.INTEGER, 1,
                   longDescription="Number of times to run the monitor. " +
                   "Set to zero to run forever")
# Loop interval
pc.defineParameter("Interval", "Loop Interval",
                   portal.ParameterType.STRING, "",
                   longDescription="Loop interval, defaults to 60 seconds " +
                   "if you leave this blank.")

# Radio gain.
pc.defineParameter("Gain", "Radio Gain",
                   portal.ParameterType.STRING, "",
                   longDescription="Radio gain. If you leave blank, defaults "+
                   "to 60 on B210s and 15 on X310s")

# Range to monitor
pc.defineParameter("Range", "Frequency Range",
                   portal.ParameterType.STRING, "3500e6-3750e6",
                   longDescription="Frequency range to scan. If you leave "+
                   "blank, defaults to 100e6-6e9")

# DST Endpoint
pc.defineParameter("DST", "ZMC URL",
                   portal.ParameterType.STRING, "",
                   longDescription="ZMC URL to send observations to")

# Auth Token
pc.defineParameter("DSTAuth", "Authorization Token",
                   portal.ParameterType.STRING, "",
                   longDescription="Authorization token for ZMC")

# Monitor ID,
pc.defineParameter("DSTMonID", "ZMC Monitor ID",
                   portal.ParameterType.STRING, "",
                   longDescription="ZMC Monitor ID. Leave this blank and " +
                   "we will figure it out")

# Optional install only
pc.defineParameter("NoRun", "Install Only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Install but do not run the monitor")

# For testing,
pc.defineParameter("TestRepo", "Test Repo",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="For testing only, use powder-testing " +
                   "local repo");

params = pc.bindParameters()

# Check parameter validity.
if params.Radio == "":
    pc.reportError(portal.ParameterError(
        "You must provide a radio", ["Radio"]))
    pass
if params.runCount < 0:
    pc.reportError(portal.ParameterError(
    "Run count must be non-negative", ["runCount"]))
    pass

pc.verifyParameters()

radioInfo = radios.allRadios[params.Radio]
radioType = radioInfo["type"]
radioURN  = radioInfo["urn"]
radioNode = radioInfo["node"]
radioMonID= radioInfo["monid"]
radioGain = defaultGains[radioType];

if radioType == "B210":
    node = request.RawPC(radioNode)
    node.component_id         = radioNode
    node.component_manager_id = radioURN
    node.disk_image           = IMAGE
else:
    # Node
    node = request.RawPC(radioNode + '-host')
    node.hardware_type = "powder-compute"
    node.disk_image           = IMAGE
    node.component_manager_id = radioURN

    radio = request.RawPC('x310')
    radio.component_id         = radioNode
    radio.component_manager_id = radioURN
    
    # Link between X310 and host -- second interface
    xiface1 = radio.addInterface("xif1")
    xiface1.component_id = "eth1"
    xiface1.addAddress(pg.IPv4Address("192.168.40.2", "255.255.255.0"))
    hiface1 = node.addInterface("hif1")
    hiface1.addAddress(pg.IPv4Address("192.168.40.1", "255.255.255.0"))

    link = request.Link("link1")
    link.addInterface(xiface1)
    link.addInterface(hiface1)
    link.bandwidth = 10 * 1000 * 1000 # 10Gbps
    link.setNoBandwidthShaping();
    link.setJumboFrames()
    pass

#
# Start up X11 VNC for display.
#
node.startVNC()

COMMAND += " -t " + radioType + " -r " + radioNode
COMMAND += " -N '" + params.Radio + "'"

if params.NoRun:
    COMMAND += " -n"
    pass
if params.TestRepo:
    COMMAND += " -T"
    pass
if params.runCount >= 0:
    COMMAND += " -c " + str(params.runCount)
    pass
if params.Gain != "":
    COMMAND += " -g " + str(params.Gain)
else:
    COMMAND += " -g " + str(radioGain)
    pass
if params.Interval != "":
    COMMAND += " -D " + str(params.Interval)
    pass
if params.DST != "":
    COMMAND += " -Z '" + str(params.DST) + "'"
    COMMAND += " -A '" + str(params.DSTAuth) + "'"
    if params.DSTMonID != "":
        COMMAND += " -I '" + str(params.DSTMonID) + "'"
    else:
        COMMAND += " -I '" + radioMonID + "'"
        pass
    pass
if params.Range != "":
    COMMAND += " -R '" + str(params.Range) + "'"
    pass

node.addService(pg.Execute(shell="sh", command=COMMAND))

request.addTour(tour)

# Final rspec.
pc.printRequestRSpec(request)
