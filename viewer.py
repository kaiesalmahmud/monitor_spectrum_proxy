#!/usr/bin/env python3
import sys
import time
import argparse
import socket
import matplotlib
import matplotlib.pyplot as pyplot
from io import StringIO
import csv
import datetime
import time

#
# Listen for connections from the monitor (running in network mode)
# Read the results and graph it. 
#
PORT      = 12237
HOST      = "localhost"

# Need to look at first line.
israwdata  = None

MySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
MySocket.bind((HOST, PORT))
MySocket.listen(5)
MySocket.settimeout(0.01)

Figure, Plot = pyplot.subplots(figsize=(14,6))
pyplot.ion()

while True:
    try:
        client_sock, address = MySocket.accept()
    except socket.timeout:
        if israwdata != None:
            pyplot.pause(1)
        continue
    except:
        raise
        
    print("New data received")

    data = ""
    while True:
        stuff = client_sock.recv(2048)
        if not stuff:
            break
        data += stuff.decode()
        pass
    client_sock.close()

    reader = csv.reader(data.splitlines())
    header = next(reader)
    if israwdata == None:
        if len(header) == 2:
            israwdata = False
        else:
            israwdata = True;
            pass
        pass
    
    freqs  = []
    powers = []
    for row in reader:
        if israwdata == True:
            # Terminator line
            freq = float(row[2])
            power = float(row[3])
            if freq != 0 and power != 0:
                freqs.append(freq)
                powers.append(power)
                pass
        else:
            freqs.append(float(row[0]))
            powers.append(float(row[1]))
            pass
        pass

    now = datetime.datetime.now()

    Plot.cla()
    Plot.plot(freqs, powers,linewidth=0.5)
    Plot.set_xlabel('Frequency')
    Plot.set_ylabel('DBm')
    Plot.set_title(now.strftime("%Y-%m-%d %H:%M:%S"))
    pyplot.tight_layout()
    pyplot.show(block=False);

    pass

