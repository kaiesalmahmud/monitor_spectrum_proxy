#!/usr/bin/perl -w

use strict;
use Carp;
use English;
use Data::Dumper;
use Getopt::Std;
use File::Temp qw(tempfile);
use File::Basename;
use POSIX qw(isatty setsid strftime);

# Drag in path stuff so we can find emulab stuff.
BEGIN { require "/etc/emulab/paths.pm"; import emulabpaths; }

#
# Proble the radio.
#
sub usage()
{
    print STDOUT "Usage: probe.pl [-dn] radiotype [radioid]\n";
    exit(-1);
}
my $optlist     = "d";
my $debug       = 0;
my $noreboot    = 0;
my $LOGFILE     = "/tmp/probe.$$";
my $CONFIG      = "/etc/rfmonitor/device_config.json";
my $MONITORETC  = "/etc/rfmonitor";
my $PROBE       = "/usr/bin/uhd_usrp_probe";
my $FIXIT       = "/usr/lib/uhd/utils/b2xx_fx3_utils -D";
my $DOWNLOADER  = "/usr/bin/uhd_images_downloader";
my $FIND        = "/usr/bin/uhd_find_devices";
my $CACHE       = "https://www.emulab.net/downloads/ettus/binaries/cache";
my $LOADER      = "/usr/bin/uhd_image_loader";
my $REBOOT      = "/bin/node_reboot";
my $GENIGET     = "/usr/bin/geni-get";
my $HOME        = $ENV{"HOME"};
my $rebooted    = 0;

#
# Turn off line buffering on output
#
$| = 1;

# Protos
sub ProbeB210();
sub ProbeX310();
sub RebootRadio();
sub DownLoadImages($);
sub fatal($);

# For SENDMAIL
use libtestbed;

#
# Parse command arguments.
#
my %options = ();
if (! getopts($optlist, \%options)) {
    usage();
}
if (defined($options{"d"})) {
    $debug = 1;
}
if (defined($options{"n"})) {
    $noreboot = 1;
}
usage()
    if (!@ARGV);

my $radiotype = shift(@ARGV);
my $radioID   = shift(@ARGV) if (@ARGV);

#
# Save off our output when not interactive, so that we can send it
# someplace useful. 
#
if (! -t) {
    open(STDOUT, ">> $LOGFILE") or
	die("opening $LOGFILE for STDOUT: $!");
    open(STDERR, ">> $LOGFILE") or
	die("opening $LOGFILE for STDERR: $!");
}

# We need the node ID for the output files.
my $nodeID = `cat $BOOTDIR/nodeid`;
if ($?) {
    fatal("Could not get nodeID");
}
chomp($nodeID);

#
# We need the local XMLRPC cert/key in case we need to power cycle
# to bring the B210 back online.
#
if (! -e "$HOME/.ssl/emulab.pem") {
    if (! -e "$HOME/.ssl") {
	if (!mkdir("$HOME/.ssl", 0750)) {
	    fatal("Could not mkdir $HOME/.ssl: $!");
	}
    }
    system("$GENIGET rpccert > $HOME/.ssl/emulab.pem");
    if ($?) {
	fatal("Could not geni-get xmlrpc cert/key");
    }
}

if ($radiotype eq "B210") {
    ProbeB210();
}
elsif ($radiotype eq "X310") {
    if (!defined($radioID)) {
	fatal("Must provide radio node ID when using an X310");
    }
    ProbeX310();
}
else {
    fatal("Do not know to probe radio type $radiotype");
}

#
# Probe a directly connected B210.
#
sub ProbeB210()
{
    if (DownLoadImages("b2xx")) {
	fatal("Could not download b2xx images");
    }
    #
    # Probe to see if we can find the B210. If not, power cycle.
    # We capture the output so we make sure its on USB 3 instead of 2.
    #
    my $output = `$PROBE 2>&1`;
    print $output;
    if ($?) {
	# Power cycle, but only once.
	if (-e "$MONITORETC/.rebooted") {
	    fatal("Could not find the radio after power cycle");
	}
	system("sudo /bin/touch $MONITORETC/.rebooted");
	system("/bin/sync");
	sleep(1);
	system("$REBOOT -s $nodeID");
	sleep(15);
	# Still here? Bad.
	fatal("Power cycle failed!");
    }
    if ($output =~ /Operating over USB (\d+)/) {
	if ($1 == 2) {
	    print "Attempting to fix USB\n";
	    system($FIXIT);
	    if ($?) {
		fatal("$FIXIT failed");
	    }
	    # Need a little delay before the probe else it fails.
	    sleep(5);
	    # Have to probe it again.
	    $output = `$PROBE 2>&1`;
	    if ($?) {
		fatal("Could not probe after USB fix");
	    }
	    if ($output !~ /Operating over USB 3/) {
		fatal("Not able to fix the USB level");
	    }
	}
    }
    else {
	fatal("Could not determine which USB is being used");
    }
    #
    # Create the config file.
    #
    my $antenna = "RX2";
    if ($nodeID =~ /cnode\-/i) {
	$antenna = "TX/RX";
    }
    system("sudo /bin/rm -f /tmp/device.cnf")
	if (-e "/tmp/device.cnf");
    
    open(CONFIG, "> /tmp/device.cnf") or
	fatal("Could not open config file for writing: $!");
    print CONFIG "{ ";
    if ($nodeID =~ /cnode\-/i) {
	print CONFIG "\"txrx_receive_hack\" : true, ";
    }
    print CONFIG "\"devices\" : { \"${nodeID}:rf0\" : ".
	"{\"name\" : \"${nodeID}:rf0\", ".
	"\"channels\" : {\"0\" : \"${antenna}\"} } } }\n";
    close(CONFIG);
    system("sudo /bin/cp -f /tmp/device.cnf $CONFIG");
    if ($?) {
	fatal("Could not copy new file to $CONFIG");
    }
    return 0;
}

#
# Proble an X310 connected by ethernet link. IP is hardwired.
#
# Reflash: Do an uhd_images_downloader, then:
#   uhd_image_loader --args "type=x300,addr=192.168.40.2,fpga=XG"
# then power cycle.
#
sub ProbeX310()
{
    # Need this for X/N 310s
    system("sudo /sbin/sysctl -w net.core.wmem_max=25000000");
    system("sudo /sbin/sysctl -w net.core.rmem_max=25000000");
    system("/local/repository/tune-cpu.sh");

    # Dustin patch that is not merged in yet.
    # Only when running as a DST monitor, not sure we want anything to
    # suddenly change for other uses of this profile.
    system("sudo patch -p3 -i /local/repository/x310-patch.diff ".
	   "  -d /usr/lib/python3/dist-packages/monitor");

    if (DownLoadImages("x3xx")) {
	fatal("Could not download x3xx images");
    }

    #
    # Use find to see if its even available. 
    #
    my $output = `$FIND 2>&1`;
    print $output;
    if ($?) {
	print "Rebooting $radioID ...\n";
	system("$REBOOT -s $radioID");
	print "Waiting a bit for trying to find it again\n";
	sleep(30);
	
	$output = `$FIND 2>&1`;
	print $output;
	if ($?) {
	    fatal("Could not find X310 after power cycle");
	}
    }
    #
    # Probe it to see if it has the correct firmware.
    #
    $output = `$PROBE 2>&1`;
    print $output;
    if ($?) {
	if ($output =~ /Error: .* Expected FPGA/) {
	    print "Flashing the X310\n";
	    system("$LOADER --args='type=x300,addr=192.168.40.2,fpga=XG'");
	}
	if ($?) {
	    fatal("Could not load required FPGA firmware");
	}
	# Must reboot and wait.
	print "Rebooting $radioID ...\n";
	system("$REBOOT -s $radioID");
	print "Waiting a bit before trying to probe it again\n";
	sleep(30);
	# Probe again, bail if it fails again.
	$output = `$PROBE 2>&1`;
	print $output;
	if ($?) {
	    fatal("Probe failed after flashing");
	}
    }
    #
    # Config file is different on an X310. And ... the cell radio is different
    # then the cbrs radio.
    #
    my $antenna = "RX2";
    if ($radioID =~ /cbrs/i) {
	$antenna = "TX/RX";
    }
    system("sudo /bin/rm -f /tmp/device.cnf")
	if (-e "/tmp/device.cnf");
    
    open(CONFIG, "> /tmp/device.cnf") or
	fatal("Could not open config file for writing: $!");
    print CONFIG "{ \"is_bs\" : true, ".
	" \"devices\" : { \"${radioID}:rf0\" : ".
	"    {\"name\" : \"${radioID}:rf0\", ".
	"     \"channels\" : {\"0\" : \"${antenna}\"} } } }\n";
    close(CONFIG);
    system("sudo /bin/cp -f /tmp/device.cnf $CONFIG");
    if ($?) {
	fatal("Could not copy new file to $CONFIG");
    }
}

sub RebootRadio()
{
    if ($noreboot) {
	print "No rebooting\n";
	return;
    }
    if ($radiotype eq "B210") {
	print "Rebooting ...\n";
	system("/bin/sync");
	system("$REBOOT -s $nodeID");
    }
    elsif ($radiotype eq "X310") {
	print "Rebooting $radioID ...\n";
	system("$REBOOT -s $radioID");
	print "Waiting a few seconds ...\n";
	sleep(10);
    }
}

#
# Having some problems with image downloading, so try more then once.
#
sub DownLoadImages($)
{
    my ($type) = @_;

    print "Downloading image type $type\n";

    system("sudo $DOWNLOADER -b $CACHE -t $type");
    if ($?) {
	sleep(5);
	system("sudo $DOWNLOADER -b $CACHE -t $type");
	return -1
	    if ($?);
    }
    return 0;
}

sub fatal($)
{
    my ($mesg) = $_[0];

    die("*** $0:\n".
	"    $mesg\n");
}
