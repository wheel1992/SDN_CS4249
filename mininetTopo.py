'''
Please add your name: Cheng Boon Yew Joseph
Please add your matric number: A0125474E
'''

import os
import sys
import atexit
import argparse
from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo
from mininet.link import Link
from mininet.node import RemoteController

net = None

topoInputFile = None

qosCommands = []

'''
Instructions to run the topo:
    1. Go to directory where this fil is.
    2. run: sudo -E python mininetTopo.py

This topo has 4 switches, 7 hosts and 11 links.
Input:
    7 4 11
    h1,s1,10
    h2,s1,10
    h3,s2,10
    h4,s2,10
    h5,s3,10
    h6,s3,10
    h7,s3,10
    s1,s2,100
    s2,s3,100
    s3,s4,100
    s1,s4,100
'''

def is_switch(str):
    return 's' in str

def is_host(str):
    return 'h' in str

def run_qos():
    for cmd in qosCommands:
        os.system(cmd)

class TreeTopo(Topo):

    def __init__(self):
		# Initialize topology
        Topo.__init__(self)

        # You can write other functions as you need.
        numHost = 0
        numSwitch = 0
        numLink = 0

        mapNodes = {}
        MEGA_BITS = 1000000

        QUEUE_DEFAULT_BW_RATIO = 0.5
        QUEUE_PREMIUM_BW_RATIO = 0.8

        '''
        Between switches, link bandwidth is 100Mbps. Configure under qosSwitchConfig
        Between host and switch, link bandwidth is 10Mbps. Configure under qosHostConfig

        QOS:
        1. Host 1, 2, 5 at least 8Mbps
        2. Other host max 5Mbps
        '''

        # qosHostConfig = ' qos=@newqos \
        #    -- --id=@newqos create QoS type=linux-htb other-config:max-rate=%s queues=0=@q0,1=@q1 \
        #    -- --id=@q0 create queue other-config:max-rate=5000000 \
        #    -- --id=@q1 create queue other-config:min-rate=8000000 other-config:max-rate=%s'
        qosHostConfig = ' qos=@newqos \
           -- --id=@newqos create QoS type=linux-htb other-config:max-rate=%s queues=0=@q0,1=@q1 \
           -- --id=@q0 create queue other-config:max-rate=%s \
           -- --id=@q1 create queue other-config:min-rate=%s other-config:max-rate=%s'

        qosSwitchConfig = ' qos=@newqos -- --id=@newqos create QoS type=linux-htb other-config:max-rate=%s'

        with open(topoInputFile, 'r') as f:
            index = 1
            for line in f:
                line = line.strip("\n ' '")
                if index == 1:
                    # i.e. 7 4 11
                    # 7 hosts
                    # 4 switches
                    # 11 links
                    firstLineItems = line.split(' ')
                    numHost = int(firstLineItems[0])
                    numSwitch = int(firstLineItems[1])
                    numLink = int(firstLineItems[2])
                    # numHost, numSwitch, numLink = [int(num) for num in line.split(' ')]

                    for hIndex in range(1, numHost + 1):
                        hostId = 'h%d' % hIndex
                        hostObj = self.addHost(hostId)
                        mapNodes[hostId] = hostObj

                        cmd = 'h{0}.setIP("10.0.0.{0}/24")'.format(hIndex)
                        os.system(cmd)

                    for sIndex in range(1, numSwitch + 1):
                        switchId = 's%d' % sIndex
                        sconfig = {'dpid': "%016x" % sIndex}
                        switchObj = self.addSwitch(switchId, **sconfig)
                        mapNodes[switchId] = switchObj


                # elif (numRowFirewall >= index):
                #     items = line.split(',')
                #     # (srcIp, destIp, port) = True
                #     self.firewallTable[(items[0], items[1], items[2])] = True
                #
                else:
                    # link rows
                    items = line.split(',')
                    nodeStr1 = items[0]
                    nodeStr2 = items[1]
                    bandwidth = int(items[2])

                    print "Read %s <---> %s on %s" % (nodeStr1, nodeStr2, bandwidth)

                    link = self.addLink(mapNodes[nodeStr1], mapNodes[nodeStr2])

                    print "Link...interface = %s" % (self.linkInfo(nodeStr1, nodeStr2))

                    # Create QoS for each link

                    # If both nodes are switches,
                    info = self.linkInfo(nodeStr1, nodeStr2)
                    maxBandwidth = str(bandwidth * MEGA_BITS)
                    defaultMaxBandwidth = str(bandwidth * MEGA_BITS * QUEUE_DEFAULT_BW_RATIO)
                    preimumMinBandwidth = str(bandwidth * MEGA_BITS * QUEUE_PREMIUM_BW_RATIO)

                    # print "MAX BW = %s" % (maxBandwidth)

                    firstPort = str('%s-eth%s' % (nodeStr1, str(info["port1"])))
                    secondPort = str('%s-eth%s' % (nodeStr2, str(info["port2"])))

                    if (is_switch(nodeStr1) and is_switch(nodeStr2)):
                        cmd = 'sudo ovs-vsctl -- set Port %s ' + qosSwitchConfig
                        qosCommands.append(cmd % (firstPort, maxBandwidth))
                        qosCommands.append(cmd % (secondPort, maxBandwidth))
                        # os.system(cmd % (firstPort, maxBandwidth))
                        # os.system(cmd % (secondPort, maxBandwidth))
                    else:

                        cmd = 'sudo ovs-vsctl -- set Port %s ' + qosHostConfig
                        if (is_switch(nodeStr1)):
                            cmd = cmd % (firstPort, maxBandwidth, defaultMaxBandwidth, preimumMinBandwidth, maxBandwidth)
                        else:
                            cmd = cmd % (secondPort, maxBandwidth, defaultMaxBandwidth, preimumMinBandwidth, maxBandwidth)
                            # os.system('sudo ovs-vsctl -- set Port %s ' + qosHostConfig % (secondPort, maxBandwidth, maxBandwidth))
                        # print cmd
                        qosCommands.append(cmd)
                        # os.system(cmd)
                index +=1

            # log.debug("Size of firewall table = %s", str(len(self.firewallTable)))
            # log.debug("Size of premium table = %s", str(len(self.premiumTable)))

        # Add hosts
        # > self.addHost('h%d' % [HOST NUMBER])
        # h1 = self.addHost('h%d' % 1)
        # h2 = self.addHost('h%d' % 2)
        # h3 = self.addHost('h%d' % 3)
        # h4 = self.addHost('h%d' % 4)
        # h5 = self.addHost('h%d' % 5)
        # h6 = self.addHost('h%d' % 6)
        # h7 = self.addHost('h%d' % 7)

        # Configure hosts ip address
#		h1.setIP('10.0.0.1', 24)
#		h2.setIP('10.0.0.2', 24)
#		h3.setIP('10.0.0.3', 24)
#		h4.setIP('10.0.0.4', 24)
#		h5.setIP('10.0.0.5', 24)
#		h6.setIP('10.0.0.6', 24)
#		h7.setIP('10.0.0.7', 24)
        # os.system('h1.setIP("10.0.0.1/24")')
        # os.system('h2.setIP("10.0.0.2/24")')
        # os.system('h3.setIP("10.0.0.3/24")')
        # os.system('h4.setIP("10.0.0.4/24")')
        # os.system('h5.setIP("10.0.0.5/24")')
        # os.system('h6.setIP("10.0.0.6/24")')
        # os.system('h7.setIP("10.0.0.7/24")')


		# Add switches
        # > sconfig = {'dpid': "%016x" % [SWITCH NUMBER]}
        # > self.addSwitch('s%d' % [SWITCH NUMBER], **sconfig)
        # sconfig = {'dpid': "%016x" % 1}
        # s1 = self.addSwitch('s%d' % 1, **sconfig)
        #
        # sconfig = {'dpid': "%016x" % 2}
        # s2 = self.addSwitch('s%d' % 2, **sconfig)
        #
        # sconfig = {'dpid': "%016x" % 3}
        # s3 = self.addSwitch('s%d' % 3, **sconfig)
        #
        # sconfig = {'dpid': "%016x" % 4}
        # s4 = self.addSwitch('s%d' % 4, **sconfig)

        # Add links
        #    linkopts = dict(bw=15, delay='2ms', loss=0, use_htb=True)
        # > self.addLink([HOST1], [HOST2])

		# linkHostOpts = dict(bw=10, delay='2ms', loss=0, use_htb=True)
        # self.addLink(h1, net.get('s1'), 0, 1)
        # self.addLink(h1, s1, 0, 1)
        # self.addLink(h2, s1, 0, 2)
        # self.addLink(h3, s2, 0, 1)
        # self.addLink(h4, s2, 0, 2)
        # self.addLink(h5, s3, 0, 1)
        # self.addLink(h6, s3, 0, 2)
        # self.addLink(h7, s3, 0, 3)

        # linkSwitchOpts = dict(bw=100, delay='2ms', loss=0, use_htb=True)
        # self.addLink(s1, s2, 3, 3)
        # self.addLink(s1, s4, 4, 2)
        # self.addLink(s2, s3, 4, 5)
        # self.addLink(s3, s4, 4, 3)


def startNetwork(inputFile):

    global topoInputFile
    topoInputFile = inputFile

    info('** Creating the tree network\n')
    topo = TreeTopo()

    global net
    net = Mininet(topo=topo, link = Link,
                  controller=lambda name: RemoteController(name, ip='192.168.56.101'),
                  listenPort=6633, autoSetMacs=True)

    info('** Starting the network\n')
    net.start()

    # Create QoS Queues
    # > os.system('sudo ovs-vsctl -- set Port [INTERFACE] qos=@newqos \
    #            -- --id=@newqos create QoS type=linux-htb other-config:max-rate=[LINK SPEED] queues=0=@q0,1=@q1,2=@q2 \
    #            -- --id=@q0 create queue other-config:max-rate=[LINK SPEED] other-config:min-rate=[LINK SPEED] \
    #            -- --id=@q1 create queue other-config:min-rate=[X] \
    #            -- --id=@q2 create queue other-config:max-rate=[Y]')

    run_qos()

    # Configure link bandwidth 10Mbps between host and switch
    # qosHostConfig = ' qos=@newqos \
    #            -- --id=@newqos create QoS type=linux-htb other-config:max-rate=10000000 queues=0=@q0,1=@q1 \
    #            -- --id=@q0 create queue other-config:max-rate=5000000 \
    #            -- --id=@q1 create queue other-config:min-rate=8000000 other-config:max-rate=10000000'
    #
    # os.system('sudo ovs-vsctl -- set Port s1-eth1 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s1-eth2 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s2-eth1 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s2-eth2 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s3-eth1 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s3-eth2 ' + qosHostConfig)
    # os.system('sudo ovs-vsctl -- set Port s3-eth3 ' + qosHostConfig)

   # Configure link bandwidth 100Mbps and QoS between switches
    # qosSwitchConfig = ' qos=@newqos \
    #            -- --id=@newqos create QoS type=linux-htb other-config:max-rate=100000000'
    #
    # os.system('sudo ovs-vsctl -- set Port s1-eth3 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s1-eth4 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s2-eth3 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s2-eth4 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s3-eth4 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s3-eth5 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s4-eth2 ' + qosSwitchConfig)
    # os.system('sudo ovs-vsctl -- set Port s4-eth3 ' + qosSwitchConfig)

    info('** Running CLI\n')
    CLI(net)

def stopNetwork():
    if net is not None:
        net.stop()
        # Remove QoS and Queues
        os.system('sudo ovs-vsctl --all destroy Qos')
        os.system('sudo ovs-vsctl --all destroy Queue')


if __name__ == '__main__':
    # Force cleanup on exit by registering a cleanup function
    atexit.register(stopNetwork)

    # Try read argument
    parser = argparse.ArgumentParser(description='Create a ArcHydro schema')
    parser.add_argument('--inputfile', metavar='path', required=True,
                        help='Topology input file')
    args = parser.parse_args()

    print "File name is..... %s" % (args.inputfile)

    # Tell mininet to print useful information
    setLogLevel('info')
    startNetwork(args.inputfile)
