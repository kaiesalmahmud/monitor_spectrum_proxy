"""Allocate a radio and run the monitor.
"""

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg
import geni.rspec.igext as ig
# Import the emulab extensions library.
import geni.rspec.emulab

#
# Setup the Tour info. We will add instructions below.
#  
tour = ig.Tour()
tour.Description(ig.Tour.TEXT, "Allocate an radio and run the monitor.");

IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU18-64-STD"
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

# Create a portal context.
pc = portal.Context()

# Create a Request object to start building the RSpec. 
request = pc.makeRequestRSpec()

pc.defineParameter("Where", "Where",
                   portal.ParameterType.STRING, ENDPOINT)

pc.defineParameter("NodeID", "Node",
                   portal.ParameterType.STRING, "nuc1")

pc.defineParameter("Type", "Radio Type",
                   portal.ParameterType.STRING, radioTypes[0], radioTypes)

pc.defineParameter("ComputeType", "Compute Type",
                   portal.ParameterType.STRING, computeTypes[0], computeTypes,
                   longDescription="Select a type for X310 compute host")

# Store results to local www directory and start nginx
pc.defineParameter("WebSave", "Local Web Server",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Save results to local directory and " +
                   "start a web server to access them. See the instructions " +
                   "for more information")

# Number of loops to run.
pc.defineParameter("runCount", "Run Count", portal.ParameterType.INTEGER, 1,
                   longDescription="Number of times to run the monitor")

# Optional install only
pc.defineParameter("NoRun", "Install Only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Install but do not run the monitor")

params = pc.bindParameters()

# Check parameter validity.
if params.Where == "":
    pc.reportError(portal.ParameterError(
        "You must provide an aggregate.", ["Where"]))
    pass
if params.NodeID == "":
    pc.reportError(portal.ParameterError(
    "You must provide a node ID", ["NodeID"]))
    pass
if params.runCount <= 0:
    pc.reportError(portal.ParameterError(
    "Run count must be greater the zero.", ["runCount"]))
    pass

pc.verifyParameters()

if params.Type == "B210":
    node = request.RawPC(params.NodeID)
    node.component_id         = params.NodeID
    node.component_manager_id = params.Where
    node.disk_image           = IMAGE
    
    COMMAND += " -t B210"
else:
    # Node
    node = request.RawPC(params.NodeID + '-host')
    if params.ComputeType == "Any":
        node.hardware_type = "powder-compute"
    else:
        node.hardware_type = params.ComputeType
        pass
    node.disk_image           = IMAGE
    node.component_manager_id = MS

    radio = request.RawPC('x310')
    radio.component_id         = params.NodeID
    radio.component_manager_id = params.Where
    
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
    
    COMMAND += " -t X310 -r " + params.NodeID
    pass

#
# Start up X11 VNC for display.
#
node.startVNC()

if params.NoRun:
    COMMAND += " -n"
    pass
if params.WebSave:
    COMMAND += " -W"
    pass
if params.runCount > 1:
    COMMAND += " -c " + str(params.runCount);
    pass
node.addService(pg.Execute(shell="sh", command=COMMAND))

#
# Added instructions.
#
if params.WebSave:
    tour.Instructions(ig.Tour.MARKDOWN,
                      "If you have enabled the __Local Web Server__ then " +
                      "you can browse the [result frequency graphs]" +
                      "(http://{host-" + node.name + "}:7998/" +
                      "frequency-graphs.html).");
    pass
request.addTour(tour)

# Final rspec.
pc.printRequestRSpec(request)
