"""Allocate an FE and run the monitor. """

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as pg
# Import the emulab extensions library.
import geni.rspec.emulab

IMAGE     = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU18-64-UHD-STD"
ENDPOINT  = "urn:publicid:IDN+bus-test2.powderwireless.net+authority+cm"
COMMAND   = "/local/repository/monitor.pl"

# Create a portal context.
pc = portal.Context()

# Create a Request object to start building the RSpec. 
request = pc.makeRequestRSpec()

pc.defineParameter("Where", "Where",
                   portal.ParameterType.STRING, ENDPOINT)

pc.defineParameter("NodeID", "Node",
                   portal.ParameterType.STRING, "ed1")

# Optionally viewer mode
pc.defineParameter("Viewer", "Viewer Mode",
                   portal.ParameterType.BOOLEAN, False,
                   longDescription="Start the monitor in network mode, use " +
                   "the viewer to see real time graph")

params = pc.bindParameters()

# Check parameter validity.
if params.Where == "":
    pc.reportError(portal.ParameterError("You must provide an aggregate.", ["Where"]))
    pass
if params.NodeID == "":
    pc.reportError(portal.ParameterError("You must provide a node ID", ["NodeID"]))
    pass

pc.verifyParameters()

node = request.RawPC(params.NodeID)
node.component_id         = params.NodeID
node.component_manager_id = params.Where
node.disk_image           = IMAGE
if params.Viewer:
    COMMAND += " -V"
    pass
node.addService(pg.Execute(shell="sh", command=COMMAND))

# Final rspec.
pc.printRequestRSpec(request)
