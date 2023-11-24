#!/usr/bin/perl -w

use strict;
use Carp;
use English;
use Data::Dumper;
use Getopt::Std;
use File::Temp qw(tempfile);
use File::Basename;
use POSIX qw(isatty setsid strftime);
use MIME::Base64;
use JSON;

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
my $optlist     = "dniVr:t:c:WD:STg:R:Z:A:I:";
my $noaction    = 0;
my $debug       = 0;
my $noinstall   = 0;
my $viewer      = 0;
my $websave     = 0;
my $dosubdir    = 0;
my $type;
my $radioID;
my $gain;
my $CONFIG      = "/etc/rfmonitor/device_config.json";
my $LOGFILE     = "/tmp/monitor.$$";
my $REPO        = dirname($PROGRAM_NAME);
my $INSTALL     = "$REPO/install.sh";
my $INSTALLNGINX= "$REPO/install-nginx.sh";
my $MONITOR     = "/usr/bin/rfmonitor";
my $MONITORETC  = "/etc/rfmonitor";
my $TAR         = "/bin/tar";
my $FIND        = "/usr/bin/uhd_find_devices";
my $PROBE       = "/usr/bin/uhd_usrp_probe";
my $FIXIT       = "/usr/lib/uhd/utils/b2xx_fx3_utils -D";
my $DOWNLOADER  = "/usr/bin/uhd_images_downloader";
my $CACHE       = "https://www.emulab.net/downloads/ettus/binaries/cache";
my $LOADER      = "/usr/bin/uhd_image_loader";
my $GENIGET     = "/usr/bin/geni-get";
my $GZIP        = "/bin/gzip";
my $CURL        = "/usr/bin/curl";
my $REBOOT      = "/usr/local/bin/node_reboot";
my $NOTIFYSLACK = "/usr/local/bin/notifyslack"; 
my $IFACE       = "rf0";  # Someday we will be able to monitor others TXs
my $WBSTORE     = "$VARDIR/save";
my $SAVEDIR     = $WBSTORE;
my $WEBDIR      = "/local/www";
my $LOOPS       = 1;
my $LOOPDELAY   = 60;
my $HOME        = $ENV{"HOME"};
my $slacked     = 0;
+my $DST;
+my $DSTAUTH;
+my $DSTMONID;

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
sub DownLoadImages($);
sub fatal($);
sub Notify($);
sub UploadObservation($);

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
if (defined($options{"W"})) {
    $websave = 1;
    if (defined($options{"S"})) {
	$dosubdir = 1;
    }
}
if (defined($options{"t"})) {
    $type = $options{"t"};
}
if (defined($options{"c"})) {
    $LOOPS = $options{"c"};
    if ($LOOPS == 0) {
	# Loop forever
	$LOOPS = 99999999;
    }
}
if (defined($options{"D"})) {
    $LOOPDELAY = $options{"D"};
}
if (defined($options{"r"})) {
    $radioID = $options{"r"};
}
if (defined($options{"T"})) {
    $ENV{"POWDERREPO"} = "powder-testing";
}
if (defined($options{"g"})) {
    $gain = $options{"g"};
}
if (defined($options{"Z"})) {
    $DST = $options{"Z"};
    if (!exists($options{"A"})) {
	fatal("Need -A argument with -Z");
    }
    if (!exists($options{"I"})) {
	fatal("Need -I argument with -Z");
    }
    $DSTAUTH  = $options{"A"};
    $DSTMONID = $options{"I"};
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
# Need pid/eid below.
my $nickname = `cat $BOOTDIR/nickname`;
chomp($nickname);
my (undef,$eid,$pid) = split(/\./, $nickname);

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
if (!$noinstall) {
    if (! -e "$MONITORETC/.ready") {
	system($INSTALL);
	if ($?) {
	    fatal("Could not install the monitor");
	}
	if (! -e "$MONITORETC/.ready") {
	    fatal("Monitor did not install properly");
	}
    }
    if ($websave && ! -e "/local/nginx-done") {
	system($INSTALLNGINX);
	if ($?) {
	    fatal("Could not install nginx");
	}
	if (! -e "/local/nginx-done") {
	    fatal("nginx did not install properly");
	}
    }
}

#
# Infer the type from node id. Fragile.
#
if (!defined($type)) {
    if ($nodeID =~ /nuc/ || $nodeID =~ /^ed\d+/) {
	$type = "B210";
    }
    else {
	$type = "X310";
    }
}
if ($type eq "B210") {
    ProbeB210();
}
elsif ($type eq "X310") {
    if (!defined($radioID)) {
	fatal("Must provide radio node ID with the -r option");
    }
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
    system("$MONITOR -g $gain -s 127.0.0.1 -p 12237");
    exit(0);
}

#
# Run the monitor. We capture the output and write a CSV temp file.
# If things go smoothly, move it to the wbstore save directory.
#
while ($LOOPS) {
    my $headered = 0;
    my $ID = ($type eq "B210" ? $nodeID : $radioID);
    
    my ($fp, $filename) = tempfile(UNLINK => 0);
    if (!$fp) {
	fatal("Could not open a temporary file");
    }
    if (! open(MON, "$MONITOR -o -n -g $gain |")) {
	fatal("Could not start ssh-keygen");
    }
    while (<MON>) {
	if ($_ !~ /^${ID}/) {
	    print $_;
	    next;
	}
	my (undef, undef, $freq, $power, $center) = split(",");
	if (!$headered) {
	    print $fp "frequency,power";
	    if (defined($center)) {
		printf $fp ",center_freq";
	    }
	    print $fp "\n";
	    $headered = 1;
	}
	printf $fp "%.3f,%.3f", $freq, $power;
	if (defined($center)) {
	    printf $fp ",%.4f", $center;
	}
	print $fp "\n";
    }
    close($fp);
    if (!close(MON)) {
	if ($websave) {
	    if ($slacked == 0 || time() - $slacked > (12 * 3600)) {
#		system("$NOTIFYSLACK 'Monitor failed'");
		$slacked = time();
	    }
	    goto skip;
	}
	fatal("Error running the monitor");
    }
    #
    # RDZ case
    #
    if (defined($DST)) {
	UploadObservation($filename);
	unlink($filename);
	goto skip;
    }
    
    $slacked = 0;
    my $now  = time();
    my $name = "${ID}:rf0-${now}.csv.gz";

    if ($websave) {
	$SAVEDIR = $WEBDIR;

	#
	# In subdir mode we are going to store the file in a subdir named
	# by the day so we do not end up a directory with 1000s of files
	# in it (and a dropdown menu with 1000s of items). 
	#
	if ($dosubdir) {
	    my $subdir = POSIX::strftime("20%y-%m-%d", localtime($now));
	    $SAVEDIR .= "/" . $subdir;

	    if (! -e $SAVEDIR) {
		if (! mkdir($SAVEDIR, 0775)) {
		    fatal("Could not mkdir $SAVEDIR: $!");
		}
		if (! chmod(0775, $SAVEDIR)) {
		    fatal("Could not chmod $SAVEDIR to 0775: $!");
		}
	    }
	}
    }
    elsif ($domain eq "emulab.net") {
	#
	# Ick, if we are running on the Mothership, have to write the file into
	# /proj instead of wbstore. Lets create a tar file that looks like the
	# wbstore file and has a known name.
	#
	$SAVEDIR = "/proj/$pid/exp/$eid";
    }
    print "Writing file to $SAVEDIR/$name\n";
    system("/bin/cat $filename | gzip > $SAVEDIR/${name}");
    if ($?) {
	fatal("Could not gzip data into the save directory.");
    }
    unlink($filename);

    if (!$websave && $domain eq "emulab.net") {
	my $mdir = "/proj/$pid/monitor";
	if (! -e $mdir) {
	    if (!mkdir($mdir, 0775)) {
		fatal("Could not mkdir $mdir: $!");
	    }
	}
	my $tfile = "$mdir/${eid}.gz";
	unlink($tfile)
	    if (-e $tfile);
	
	system("$TAR -cf ${tfile}.tmp -C /proj $pid/exp/$eid/$name");
	if ($?) {
	    fatal("Could not create dopey tar file");
	}
	system("/bin/mv ${tfile}.tmp $tfile");
	if ($?) {
	    fatal("Could not move dopey tar file into place");
	}
    }
  skip:
    $LOOPS--;
    sleep($LOOPDELAY)    
	if ($LOOPS);
}
if ($websave) {
    system("/bin/touch $WEBDIR/DONE");
}
Notify("Worked") if ($debug);
exit(0);

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
    system("sudo /bin/rm -f /tmp/device.cnf")
	if (-e "/tmp/device.cnf");
    
    open(CONFIG, "> /tmp/device.cnf") or
	fatal("Could not open config file for writing: $!");
    print CONFIG "{ \"devices\" : { \"${nodeID}:rf0\" : ".
	"{\"name\" : \"${nodeID}:rf0\", ".
	"\"channels\" : {\"0\" : \"RX2\"} } } }\n";
    close(CONFIG);
    system("sudo /bin/cp -f /tmp/device.cnf $CONFIG");
    if ($?) {
	fatal("Could not copy new file to $CONFIG");
    }
    # Default gain for B210s
    $gain = 85 if (!defined($gain));
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
    system("sudo /sbin/sysctl -w net.core.wmem_max=24862979");

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
    # Default gain for X310s
    $gain = 10 if (!defined($gain));
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

#
# RDZ
#
sub UploadObservation($)
{
    my ($filename) = @_;
    my $stamp   = POSIX::strftime("20%y-%m-%dT%H:%M:%SZ", gmtime(time()));
    my $min_freq;
    my $max_freq;
    my $data;
    
    if (open(DATA, $filename)) {
	# Header
	$data = <DATA>;
	# First line to get min freq.
	my $line = <DATA>;
	$data .= $line;
	($min_freq) = split(",", $line);
	while (<DATA>) {
	    $line = $_;
	    $data .= $line;
	}
	# Last line to get max freq.
	($max_freq) = split(",", $line);
	close(DATA);
    }
    else {
	fatal("Could not open $filename: $!");
    } 
    my $request = {
	"monitor_id"  => $DSTMONID,
	"types"       => "inline,sweep",
	"format"      => "psd-csv-inline",
	"min_freq"    => $min_freq * 1000000,
	"max_freq"    => $max_freq * 1000000,
	"starts_at"   => $stamp,
    };
    print Dumper($request);
    $request->{'data'} = encode_base64($data);

    my $command = "$CURL -k -X POST -H 'X-Api-Token: $DSTAUTH' " .
	"-d \@- $DST/observations";

    print "$command\n";

    #
    # Pipe the json encoded request into curl.
    #
    my $pid = open(PIPE, "|-");
    if (!defined($pid)) {
	print STDERR "UploadObservation; popen failed!\n";
	return;
    }
    if (!$pid) {
	open(STDERR, ">&STDOUT");
	exec($command);
	die("UploadObservation: exec failed\n");
    }
    eval { print PIPE encode_json($request); };
    if ($@) {
	print STDERR $@;
    }
    close(PIPE);
}

my $exiting = 0;

sub fatal($)
{
    my ($mesg) = $_[0];
    $exiting = 1;
    Notify($mesg);
    system("/bin/cp $LOGFILE /proj/$pid");

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
