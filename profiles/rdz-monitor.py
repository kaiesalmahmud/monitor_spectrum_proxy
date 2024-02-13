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
tour.Description(ig.Tour.TEXT, "Allocate a radio and run the monitor.");

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
# Default gains by RadioType.
defaultGains = {
    "B210" : 60,
    "X310" : 15,
}
# All radio info
allRadios = {
    "Bookstore Nuc1" : {
        "urn"  : 'urn:publicid:IDN+bookstore.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "02661b49-a44a-4ab7-af1a-67c4bfdef418",
    },
    "Bookstore Nuc2" : {
        "urn"  : 'urn:publicid:IDN+bookstore.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "minid": "0df55eb2-d61c-4e5b-ad8f-406d4ae5a26a",
    },
    "CPG Nuc1" : {    
        "urn"  : 'urn:publicid:IDN+cpg.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "27fe4310-b949-4074-9e25-91f38f1e905f",
    },
    "CPG Nuc2" : {    
        "urn"  : 'urn:publicid:IDN+cpg.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "299cac8d-f8af-4ca9-b77e-9a548e422309",
    },
    "EBC Nuc1" : {
        "urn"  : 'urn:publicid:IDN+ebc.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "6178ac96-5320-4a70-8210-53ece96bbe7d",
    },
    "EBC Nuc2" : {
        "urn"  : 'urn:publicid:IDN+ebc.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "5c4358aa-5906-4a32-aeca-f51bfe353c37",
    },
    "Guesthouse Nuc1" : {
        "urn"  : 'urn:publicid:IDN+guesthouse.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "4f6403ae-d2c3-484f-8dea-febd26b8d214",
    },
    "Guesthouse Nuc2" : {
        "urn"  : 'urn:publicid:IDN+guesthouse.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "85ae79a1-bf59-431f-91f5-c5f9e4a930ce",
    },
    "Humanities Nuc1" : {
        "urn"  : 'urn:publicid:IDN+humanities.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "9fa2b8e4-19dd-434f-94ce-8fb55dabe60c",
    },
    "Humanities Nuc2" : {
        "urn"  : 'urn:publicid:IDN+humanities.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "bcab7763-78c5-4574-b8dc-5935b2f97fd7",
    },
    "Law Nuc1" : {
        "urn"  : 'urn:publicid:IDN+law73.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "20ffbe53-12c0-4da4-aefb-601aa46519e3",
    },
    "Law Nuc2" : {
        "urn"  : 'urn:publicid:IDN+law73.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "06cd9bd4-0e4f-4ee1-a069-d578a5aa8b8d",
    },
    "Madsen Nuc1" : {
        "urn"  : 'urn:publicid:IDN+madsen.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "d444cf54-2a01-49e3-aa9e-77f521b6824d",
    },
    "Madsen Nuc2" : {
        "urn"  : 'urn:publicid:IDN+madsen.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "0c5b9142-d68a-4f26-b742-1ae9e047466f",
    },
    "Moran Nuc1" : {
        "urn"  : 'urn:publicid:IDN+moran.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "ff7ce1fe-e023-40b6-b7c4-1b5aeaa62590",
    },
    "Moran Nuc2" : {
        "urn"  : 'urn:publicid:IDN+moran.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "54c79086-3ff2-4e45-8860-34aa299a2c07",
    },
    "Sagepoint Nuc1" : {
        "urn"  : 'urn:publicid:IDN+sagepoint.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "5bcf5279-0d12-4bce-a82c-730015199d7e",
    },
    "Sagepoint Nuc2" : {
        "urn"  : 'urn:publicid:IDN+sagepoint.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "a44a845e-e207-4299-834c-1da950e50966",
    },
    "WEB Nuc1" : {
        "urn"  : 'urn:publicid:IDN+web.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc1",
        "monid": "23276b37-8005-43b8-a551-feaec90a9fa9",
    },
    "WEB Nuc2" : {
        "urn"  : 'urn:publicid:IDN+web.powderwireless.net+authority+cm',
        "type" : "B210",
        "node" : "nuc2",
        "monid": "9f63213f-3165-4666-a4a5-f506bb3efb29",
    },
    "cbrssdr1-bes" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-bes",
        "monid": "1680c98a-22c6-4717-bea6-3cc5062af1b4",
    },
    "cbrssdr1-browning" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-browning",
        "monid": "81d925b9-98a0-4e35-b0a2-a771259b2e66",
    },
    "cbrssdr1-dentistry" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-dentistry",
        "monid": "14b0759c-29be-4fdd-acef-6d1ffd248678",
    },
    "cbrssdr1-fm" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-fm",
        "monid": "96aa8db3-ad94-4986-98f4-3a9c8cf59b1b",
    },
    "cbrssdr1-honors" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-honors",
        "monid": "94fa37e6-029e-4998-908c-e6cac8139da2",
    },
    "cbrssdr1-hospital" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-hospital",
        "monid": "8065a962-cb35-4169-9de5-04075c1b13bb",
    },
    "cbrssdr1-meb" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-meb",
        "monid": "39a7e217-9194-421a-b20f-912819200565",
    },
    "cbrssdr1-ustar" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cbrssdr1-ustar",
        "monid": "3258a2dd-9c89-4ce2-8bcf-1839dfb42d98",
    },
    "cellsdr1-bes" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cellsdr1-bes",
        "monid": "a6e78b5f-e633-4ba3-9d6a-c25de05d114d",
    },
    "cellsdr1-hospital" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "X310",
        "node" : "cellsdr1-hospital",
        "monid": "505930a4-eddf-4fe9-85ec-1a1369707f74",
    },
    "cnode-ebc" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-ebc",
        "monid": "c1cb3c51-a60f-4a41-a9bf-d6ec2d510935",
    },
    "cnode-guesthouse" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-guesthouse",
        "monid": "a56f8d4f-0c8b-47a3-aa42-9237da304398",
    },
    "cnode-mario" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-mario",
        "monid": "65373435-2460-416f-88ce-427b89575436",
    },
    "cnode-moran" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-moran",
        "monid": "203e649a-af22-48ba-b837-de8b2f25d327",
    },
    "cnode-ustar" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-ustar",
        "monid": "431dfb6f-1ecc-4eec-b42b-ac2ab75808fd",
    },
    "cnode-wasatch" : {
        "urn"  : 'urn:publicid:IDN+emulab.net+authority+cm',
        "type" : "B210",
        "node" : "cnode-wasatch",
        "monid": "d6bbc250-dacc-4804-8efd-9029c29f1797",
    },
}
# The Select list provides index into above dict.
radioSelect = []
for key in allRadios:
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

radioInfo = allRadios[params.Radio]
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
