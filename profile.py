"""Allocate an FE and run the monitor. """

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg
# Import the emulab extensions library.
import geni.rspec.emulab

IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU18-64-STD"
ENDPOINT  = "urn:publicid:IDN+bus-test2.powderwireless.net+authority+cm"
MS        = "urn:publicid:IDN+emulab.net+authority+cm"
COMMAND   = "/local/repository/monitor.pl"

#
# Two types of situations; B210 directly connected, and X310 ethernet connected.
# AT the moment, B210 means an FE and X310 means a base station.
#
radioTypes = [
    ('B210', 'B210'),
    ('X310', 'X310'),
]
computeTypes = [
    ('powder-compute', 'Any'),
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
                   portal.ParameterType.STRING, "ed1")

pc.defineParameter("Type", "Radio Type",
                   portal.ParameterType.STRING, radioTypes[0], radioTypes)

pc.defineParameter("ComputeType", "Compute Type",
                   portal.ParameterType.STRING, computeTypes[0], computeTypes,
                   longDescription="Select a type for X310 compute host")

# Optional install only
pc.defineParameter("NoRun", "Install Only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Install but do not run the monitor.")

# Optional viewer only mode
pc.defineParameter("Viewer", "Viewer only",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Run the monitor in viewer mode.")

params = pc.bindParameters()

# Check parameter validity.
if params.Where == "":
    pc.reportError(portal.ParameterError("You must provide an aggregate.", ["Where"]))
    pass
if params.NodeID == "":
    pc.reportError(portal.ParameterError("You must provide a node ID", ["NodeID"]))
    pass

if params.NoRun and params.Viewer:
    pc.reportError(portal.ParameterError("Please check only one", ["Viewer"]))
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
elif params.Viewer:
    COMMAND += " -V"
    pass
node.addService(pg.Execute(shell="sh", command=COMMAND))

# Final rspec.
pc.printRequestRSpec(request)
