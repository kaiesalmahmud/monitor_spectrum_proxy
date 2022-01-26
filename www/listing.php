<?php
#
# Copyright (c) 2000-2022 University of Utah and the Flux Group.
# 
# {{{EMULAB-LICENSE
# 
# This file is part of the Emulab network testbed software.
# 
# This file is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
# 
# This file is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
# License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this file.  If not, see <http://www.gnu.org/licenses/>.
# 
# }}}
#
$listing = array();

function getFileList($archive)
{
    global $listing;
    $dir = ($archive ? "./archive" : ".");

    // open pointer to directory and read list of files
    $d = dir($dir);
    if (!$d) {
        exit("Failed to open $dir for reading");
    }
    while (($entry = $d->read()) !== FALSE) {
        #
        # Only the .gz files
        #
        if (!preg_match("/\.gz$/", $entry)) {
            continue;
        }
        #
        # And only the time stamped ones, ignore the symlinks
        #
        if (is_link($entry)) {
            continue;
        }
        $listing[] = [
            'name'     => $entry,
            'lastmod'  => filemtime("${dir}/${entry}"),
            'archived' => $archive,
        ];
    }        
    $d->close();
}
getFileList(0);
if (is_readable("archive")) {
    getFileList(1);
}

header("Content-Type: text/plain");
header("Expires: Mon, 26 Jul 1997 05:00:00 GMT");
header("Cache-Control: no-cache, must-revalidate");
header("Pragma: no-cache");

echo json_encode($listing);

?>
