#!/usr/bin/perl -w

use strict;
use Carp;
use English;
use Data::Dumper;
use Getopt::Std;
use File::Temp qw(tempfile);
use File::Basename;
use POSIX qw(isatty setsid);

# Drag in path stuff so we can find emulab stuff.
BEGIN { require "/etc/emulab/paths.pm"; import emulabpaths; }

#
# Install the monitor, run a few iterations, copy the CSV files to the
# the wbstore directory for transport back to the Mothership.
#
sub usage()
{
    print STDOUT "Usage: monitor [-dniV] [-t type] [-r radio]\n";
    exit(-1);
}
my $optlist     = "dniVr:t:";
my $noaction    = 0;
my $debug       = 0;
my $noinstall   = 0;
my $viewer      = 0;
my $type        = "B210";
my $radioID;
my $CONFIG      = "/etc/rfmonitor/device_config.json";
my $LOGFILE     = "/tmp/monitor.$$";
my $REPO        = "/local/repository";
my $INSTALL     = "$REPO/install.sh";
my $MONITOR     = "/usr/bin/rfmonitor";
my $MONITORETC  = "/etc/rfmonitor";
my $FIND        = "/usr/bin/uhd_find_devices";
my $PROBE       = "/usr/bin/uhd_usrp_probe";
my $FIXIT       = "/usr/lib/uhd/utils/b2xx_fx3_utils -D";
my $LOADER      = "/usr/bin/uhd_image_loader";
my $GENIGET     = "/usr/bin/geni-get";
my $GZIP        = "/bin/gzip";
my $REBOOT      = "/usr/local/bin/node_reboot";
my $IFACE       = "rf0";  # Someday we will be able to monitor others TXs
my $SAVEDIR     = "$VARDIR/save";
my $LOOPS       = 1;
my $LOOPDELAY   = 60;
my $HOME        = $ENV{"HOME"};

#
# HOME will not be defined until new images are built.
#
if (!defined($HOME)) {
    $HOME = "/users/geniuser";
    $ENV{"HOME"} = $HOME;
    $ENV{"USER"} = "geniuser";
}

#
# Turn off line buffering on output
#
$| = 1;

# Protos
sub ProbeB210();
sub ProbeX310();
sub fatal($);
sub Notify($);

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
if (defined($options{"i"})) {
    $noinstall = 1;
}
if (defined($options{"n"})) {
    $noaction = 1;
}
if (defined($options{"V"})) {
    $viewer = 1;
}
if (defined($options{"t"})) {
    $type = $options{"t"};
}
if (defined($options{"r"})) {
    $radioID = $options{"r"};
}

#
# Save off our output when not interactive, so that we can send it
# someplace useful. 
#
if (! -t || ($viewer && !$debug)) {
    open(STDOUT, ">> $LOGFILE") or
	die("opening $LOGFILE for STDOUT: $!");
    open(STDERR, ">> $LOGFILE") or
	die("opening $LOGFILE for STDERR: $!");
}

if ($type ne "B210" && !defined($radioID)) {
    fatal("Must provide radio node ID with the -r option");
}

# We need the node ID for the output files.
my $nodeID = `cat $BOOTDIR/nodeid`;
if ($?) {
    fatal("Could not get nodeID");
}
chomp($nodeID);
my $domain = `cat $BOOTDIR/mydomain`;
if ($?) {
    fatal("Could not get domain");
}
chomp($domain);

# We do not run wbstore on the Mothership, so these have to copied to /proj.
if ($type ne "B210") {
    my $nickname = `cat $BOOTDIR/nickname`;
    chomp($nickname);
    my (undef,$eid,$pid) = split(/\./, $nickname);

    $SAVEDIR = "/proj/$pid/exp/$eid";
    print "Changing SAVEDIR to $SAVEDIR\n";
}

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

# Install the monitor packages.
if (!$noinstall && ! -e "$MONITORETC/.ready") {
    system($INSTALL);
    if ($?) {
	fatal("Could not install the monitor");
    }
    if (! -e "$MONITORETC/.ready") {
	fatal("Monitor did not install properly");
    }
}

if ($type eq "B210") {
    ProbeB210();
}
elsif ($type eq "X310") {
    ProbeX310();
}
else {
    fatal("Do not know to probe radio type $type");
}

if ($noaction) {
    print "Exiting without doing anything\n";
    exit(0);
}
#
# In viewer mode, just start the monitor and exit.
#
if ($viewer) {
    if (!$debug) {
	if (TBBackGround($LOGFILE)) {
	    exit(0);
	}
    }
    system("$MONITOR -g 85 -s 127.0.0.1 -p 12237");
    exit(0);
}

#
# Run the monitor. We capture the output and write a CSV temp file.
# If things go smoothly, move it to the wbstore save directory.
#
while ($LOOPS) {
    my $ID = ($type eq "B210" ? $nodeID : $radioID);
    
    my ($fp, $filename) = tempfile(UNLINK => 0);
    if (!$fp) {
	fatal("Could not open a temporary file");
    }
    print $fp "frequency,power\n";
    
    if (! open(MON, "$MONITOR -o -n -g 85 |")) {
	fatal("Could not start ssh-keygen");
    }
    while (<MON>) {
	if ($_ !~ /^${ID}/) {
	    print $_;
	    next;
	}
	my (undef, undef, $freq, $power) = split(",");
	printf $fp "%.3f,%.3f\n", $freq, $power;
    }
    close($fp);
    if (!close(MON)) {
	fatal("Error running the monitor");
    }
    my $now  = time();
    my $name = "${ID}:rf0-${now}.csv.gz";
    print "Writing file to $SAVEDIR/$name\n";
    system("/bin/cat $filename | gzip > $SAVEDIR/$name");
    if ($?) {
	fatal("Could not gzip data into the save directory.");
    }
    unlink($filename);
    $LOOPS--;
    sleep($LOOPDELAY)    
	if ($LOOPS);
}
Notify("Worked") if ($debug);
exit(0);

#
# Probe a directly connected B210.
#
sub ProbeB210()
{
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
    open(CONFIG, "> $CONFIG") or
	fatal("Could not open config file for writing: $!");
    print CONFIG "{ \"devices\" : { \"${nodeID}:rf0\" : ".
	"{\"name\" : \"${nodeID}:rf0\", ".
	"\"channels\" : {\"0\" : \"RX2\"} } } }\n";
    close(CONFIG);
    return 0;
}

#
# Proble an X310 connected by ethernet link. IP is hardwired.
#
sub ProbeX310()
{
    # Need this for X/N 310s
    system("sudo /sbin/sysctl -w net.core.wmem_max=24862979");

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
	if ($output =~ /Error: Expected FPGA/) {
	    print "Flashing the X310\n";
	    system("$LOADER --args='type=x300,addr=192.168.40.2'");
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
    
    open(CONFIG, "> $CONFIG") or
	fatal("Could not open config file for writing: $!");
    print CONFIG "{ \"is_bs\" : true, ".
	" \"devices\" : { \"${radioID}:rf0\" : ".
	"    {\"name\" : \"${radioID}:rf0\", ".
	"     \"channels\" : {\"0\" : \"${antenna}\"} } } }\n";
    close(CONFIG);
}

sub Notify($)
{
    my ($mesg) = $_[0];

    if (! -t) {
	SENDMAIL("stoller\@flux.utah.edu",
		 "Spectrum Monitoring Experiment: ${nodeID}.${domain}",
		 $mesg . "\n\n", undef,
		 "X-Spectrum-Monitor: ${nodeID}.${domain} ",
		 $LOGFILE);
	# So it has time to depart before experiment termination.
	sleep(10);
    }
}

my $exiting = 0;

sub fatal($)
{
    my ($mesg) = $_[0];
    $exiting = 1;
    Notify($mesg);

    die("*** $0:\n".
	"    $mesg\n");
}

END {
    return
	if ($exiting);
    
    if ($?) {
	my $exitstatus = $?;
	Notify("Unexpected exit");
	$? = $exitstatus;
    }
}
