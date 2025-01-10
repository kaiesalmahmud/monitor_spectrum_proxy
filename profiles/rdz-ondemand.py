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
tour.Description(ig.Tour.TEXT, "Allocate all radios and run the monitor");

#
# Defaults for this setup
#
IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-GRE310"
MS        = "urn:publicid:IDN+emulab.net+authority+cm"
COMMAND   = "/local/repository/monitor.pl -K "
RANGE     = "3350e6-3750e6"
RUNCOUNT  = 1
INTERVAL  = 10

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

# Request a set of radios. We will default to all.
pc.defineParameter("Radios", "Radio",
                   portal.ParameterType.STRING, [], radioSelect,
                   min=0, multiValue=1, itemDefaultValue=radioSelect[0][0])

# Number of loops to run.
pc.defineParameter("runCount", "Run Count",
                   portal.ParameterType.INTEGER, RUNCOUNT,
                   longDescription="Number of times to run the monitor. " +
                   "Set to zero to run forever")
# Loop interval
pc.defineParameter("Interval", "Loop Interval",
                   portal.ParameterType.INTEGER, INTERVAL,
                   longDescription="Loop interval, defaults to 10 seconds " +
                   "if you leave this blank.")

# Range to monitor
pc.defineParameter("Range", "Frequency Range",
                   portal.ParameterType.STRING, RANGE,
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

# Optional install only
pc.defineParameter("NoRun", "Install Only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Install but do not run the monitor")

# For testing,
pc.defineParameter("TestRepo", "Test Repo",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="For testing only, use powder-testing " +
                   "local repo");
# Retrieve the values the user specifies during instantiation.
params = pc.bindParameters()

# Check parameter validity.
if params.runCount < 0:
    pc.reportError(portal.ParameterError(
    "Run count must be non-negative", ["runCount"]))
    pass

pc.verifyParameters()


# Set up the common part of the command
#
if params.NoRun:
    COMMAND += " -n"
    pass
if params.TestRepo:
    COMMAND += " -T"
    pass
if params.runCount >= 0:
    COMMAND += " -c " + str(params.runCount)
    pass
if params.Interval != "":
    COMMAND += " -D " + str(params.Interval)
    pass
if params.DST != "":
    COMMAND += " -Z '" + str(params.DST) + "'"
    COMMAND += " -A '" + str(params.DSTAuth) + "'"
    pass
if params.Range != "":
    COMMAND += " -R '" + str(params.Range) + "'"
    pass

if len(params.Radios) == 0:
    params.Radios = radios.allRadios.keys()
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
        pass

    command += " -I '" + radioMonID + "'"
    command += " -t " + radioType + " -r " + radioNode
    command += " -N '" + radioname + "'"
    command += " -g " + str(radioGain)
    node.addService(pg.Execute(shell="sh", command=command))
    pass

request.addTour(tour)

# Final rspec.
pc.printRequestRSpec(request)
