
$(document).ready(function () {
    var options = {
	"selector"  : ".frequency-graph-div",
	"url"       : window.location.origin,
	"cluster"   : null,
	"node_id"   : null,
	"iface"     : null,
	"archived"  : false,
	"baseline"  : true,
    };
    ShowFrequencyGraph(options);
});

