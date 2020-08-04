#!/usr/bin/perl -w

use strict;
use Carp;
use English;
use Data::Dumper;
use Getopt::Std;
use File::Temp qw(tempfile);
use POSIX qw(isatty setsid);

# Drag in path stuff so we can find emulab stuff.
BEGIN { require "/etc/emulab/paths.pm"; import emulabpaths; }

#
# Install the monitor, run a few iterations, copy the CSV files to the
# the wbstore directory for transport back to the Mothership.
#
sub usage()
{
    print STDOUT "Usage: monitor [-d] [-n] [i]\n";
    exit(-1);
}
my $optlist     = "dni";
my $impotent    = 0;
my $debug       = 0;
my $noinstall   = 0;
my $LOGFILE     = "/tmp/monitor.$$";
my $REPO        = "/local/repository";
my $INSTALL     = "$REPO/install.sh";
my $MONITOR     = "/usr/bin/rfmonitor";
my $MONITORETC  = "/etc/rfmonitor";
my $PROBE       = "/usr/bin/uhd_usrp_probe";
my $FIXIT       = "/usr/lib/uhd/utils/b2xx_fx3_utils -D";
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
if (defined($options{"n"})) {
    $impotent = 1;
}
if (defined($options{"i"})) {
    $noinstall = 1;
}

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
my $domain = `cat $BOOTDIR/mydomain`;
if ($?) {
    fatal("Could not get domain");
}
chomp($domain);

#
# We need the local XMLRPC cert/key in case we need to power cycle
# to bring the B210 back online.
#
if (! -e "$HOME/.ssl/emulab.pem") {
    if (! -e "$HOME/.ssl") {
	if (!mkdir("$HOME/.ssl", 0750)) {
	    fatal("Could not mkdir $HOME/.ssl");
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
# Run the monitor. We capture the output and write a CSV temp file.
# If things go smoothly, move it to the wbstore save directory.
#
while ($LOOPS) {
    my ($fp, $filename) = tempfile(UNLINK => 0);
    if (!$fp) {
	fatal("Could not open a temporary file");
    }
    print $fp "frequency,power\n";
    
    if (! open(MON, "$MONITOR -o -n |")) {
	fatal("Could not start ssh-keygen");
    }
    while (<MON>) {
	if ($_ !~ /^${nodeID}/) {
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
    my $name = "${nodeID}:rf0-${now}.csv.gz";
    system("/bin/cat $filename | gzip > $SAVEDIR/$name");
    if ($?) {
	fatal("Could not gzip data into the save directory.");
    }
    unlink($filename);
    $LOOPS--;
    sleep($LOOPDELAY)    
	if ($LOOPS);
}
Notify("Worked");
exit(0);

sub Notify($)
{
    my ($mesg) = $_[0];

    if (! -t) {
	SENDMAIL("stoller\@flux.utah.edu",
		 "Spectrum Monitoring Experiment: ${nodeID}.${domain}",
		 $mesg . "\n\n", undef,
		 "X-Spectrum-Monitor: ${nodeID}.${domain} ",
		 $LOGFILE);
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
