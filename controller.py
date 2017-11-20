'''
Please add your name: Cheng Boon Yew Joseph
Please add your matric number: A0125474E
'''

import sys
import os
import time

from sets import Set

from pox.core import core

import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
import pox.openflow.spanning_tree
import pox.lib.packet as pkt

from pox.lib.revent import *
from pox.lib.util import str_to_bool, dpid_to_str
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.packet.ethernet import ethernet, ETHER_BROADCAST
from pox.lib.packet.tcp import tcp
from pox.lib.packet.ipv4 import ipv4
from pox.lib.packet.arp import arp


from csv import DictReader

log = core.getLogger()

# Timeout for flows
FLOW_IDLE_TIMEOUT = 10

# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0
numRowFirewall = 0
numRowPreimum = 0

priorityLearn = 1
priorityPremium = 10
priorityFirewall = 100

class Entry(object):
    def __init__(self, port, mac):
        self.port = port
        self.mac = mac

    def __eq__(self, other):
        if type(other) == tuple:
            return (self.port,self.mac)==other
        else:
            return (self.port,self.mac)==(other.port,other.mac)

    def __ne__ (self, other):
        return not self.__eq__(other)

def dpid_to_mac (dpid):
    return EthAddr("%012x" % (dpid & 0xffFFffFFffFF,))

class Controller(EventMixin):
    def __init__(self, policyFile):
        self.listenTo(core.openflow)
        core.openflow_discovery.addListeners(self)

        # Initialize forwarding table
        # self.macToPort = {}
        self.forwardTable = {}
        self.lost_buffers = {}

        # Initialize firewall table
        self.firewallTable = {}

        # Initialize premium table
        self.premiumTable = {}

        self.policyFile = policyFile;

        self.hold_down_expired = _flood_delay == 0




    def read_Policy(self, file):
        with open(file, 'r') as f:
            index = 0
            for line in f:
                line = line.strip("\n ' '")
                if index == 0:
                    firstLineItems = line.split(' ')
                    numRowFirewall = int(firstLineItems[0])
                    numRowPreimum = int(firstLineItems[1])

                elif (numRowFirewall >= index):
                    items = line.split(',')
                    # (srcIp, destIp, port) = True
                    self.firewallTable[(items[0], items[1], items[2])] = True

                else:
                    # left the premium lines
                    self.premiumTable[(line)] = True

                index +=1

            log.debug("Size of firewall table = %s", str(len(self.firewallTable)))
            log.debug("Size of premium table = %s", str(len(self.premiumTable)))

#            reader = DictReader(f, delimiter = ",")
##            policies = {}
#            for row in reader:
#                log.info("...ROW = "
#                self.firewallTable[(row[0], row[1])] = row[2]
##                log.info("*** Added firewall rule in src=%s, dest=%s, port=%s", row[0], row[1], row[2])
##        return policies

    def check_premium(self, srcIp):
        try:
            entry = self.premiumTable[(str(srcIp))]
            log.debug("CHECK PREMIUM src=%s, result=%s", str(srcIp), str(entry))
            return entry

        except KeyError:
            log.debug("NOT IN PREMIUM src=%s", str(srcIp))
            return False


    def check_rule(self, srcIp, destIp, port):
        try:
            log.debug("CHECK RULE src=%s, dst=%s, port=%s", str(srcIp), str(destIp), str(port))
            entry = self.firewallTable[(str(srcIp), str(destIp), str(port))]
            return entry

        except KeyError:
            log.debug("NOT IN FIREWALL src=%s, dst=%s port=%s", str(srcIp), str(destIp), str(port))
            return False

    def _send_lost_buffers (self, dpid, ipaddr, macaddr, port):
        if (dpid, ipaddr) in self.lost_buffers:
            bucket = self.lost_buffers[(dpid,ipaddr)]
            del self.lost_buffers[(dpid,ipaddr)]
            log.debug("Sending %i buffered packets to %s from %s" % (len(bucket), ipaddr, dpid_to_str(dpid)))
            for _,buffer_id,in_port in bucket:
                po = of.ofp_packet_out(buffer_id=buffer_id,in_port=in_port)
                po.actions.append(of.ofp_action_dl_addr.set_dst(macaddr))
                po.actions.append(of.ofp_action_output(port = port))
                core.openflow.sendToDPID(dpid, po)

    def _handle_PacketIn (self, event):
        # install entries to the route table
        #
        # def install_enqueue(event, packet, outport, q_id):
        #     self.macToPort[packet.src] = event.port

        # Check the packet and decide how to route the packet
        def forward(message = None):
            # dpid => switch (i)
            dpid = event.connection.dpid
            # port of a switch
            inport = event.port
            packet = event.parsed

            log.debug("Add to forward table src=%s, port=%s" % (packet.src, event.port))
            # self.macToPort[packet.src] = event.port

            if dpid not in self.forwardTable:
                self.forwardTable[dpid] = {}

            if packet.type == ethernet.LLDP_TYPE:
                # Ignore LLDP packets
                return

            if isinstance(packet.next, ipv4):
                log.debug("IPV4 packet s=%i, sp=%i src=%s => dst=%s", dpid, inport,
                packet.next.srcip, packet.next.dstip)

                if (packet.next.protocol == packet.next.TCP_PROTOCOL):
                    # Get TCP payload in IPv4
                    tcpPacket = packet.next.payload
                    log.debug("TCP payload srcport= %s dstport=%s", str(tcpPacket.srcport), str(tcpPacket.dstport))

                    # Check firewall
                    if self.check_rule(packet.next.srcip, packet.next.dstip,  tcpPacket.dstport) or self.check_rule(packet.next.dstip, packet.next.srcip, tcpPacket.dstport):
                        log.warning("Firewall DROP between %s <--> %s on port %s", str(packet.next.srcip), str(packet.next.dstip), str(tcpPacket.dstport))
                        drop(priorityFirewall)
                        return


                # Send any waiting packets...
                self._send_lost_buffers(dpid, packet.next.srcip, packet.src, inport)

                # Learn or update forwarding table
                log.debug("s=%i, sp=%i LEARN or UPDATE src=%s", dpid, inport, str(packet.next.srcip))
                self.forwardTable[dpid][packet.next.srcip] = Entry(inport, packet.src)

                # Try to forward to destination by checking port
                dstip = packet.next.dstip
                if (dstip in self.forwardTable[dpid]):
                    # Got the port info to send out
                    dstport = self.forwardTable[dpid][dstip].port
                    dstmac = self.forwardTable[dpid][dstip].mac

                    if dstport == inport:
                        # Same port for destination and switch..
                        log.warning("s=%i, sp=%i NOT SEND PACKET for dst=%s with same port" % (dpid, inport, str(dstip)))
                    else:
                        log.debug("s=%i, sp=%i INSTALL FLOW for src=%s => dst=%s out port=%i"
                    % (dpid, inport, packet.next.srcip, dstip, dstport))

                        actions = []
                        if self.check_premium(packet.next.dstip):
                            actions.append(of.ofp_action_enqueue(port = dstport, queue_id = 1))
                        else:
                            actions.append(of.ofp_action_output(port = dstport))

                        # actions.append(of.ofp_action_output(port = dstport))
                        actions.append(of.ofp_action_dl_addr.set_dst(dstmac))
                        match = of.ofp_match.from_packet(packet, inport)
                        match.dl_src = None # Wildcard source MAC

                        msg = of.ofp_flow_mod(command=of.OFPFC_ADD, idle_timeout=FLOW_IDLE_TIMEOUT, hard_timeout=of.OFP_FLOW_PERMANENT, buffer_id=event.ofp.buffer_id, actions=actions, match=of.ofp_match.from_packet(packet, inport))
                        msg.priority = priorityPremium
                        # if self.check_premium(packet.next.dstip):
                        #     log.debug("PRIORITY dst ip=%s has priority of 100!!!!!" % packet.next.dstip)
                        #     msg.priority = 100
                        # else:
                        #     log.debug("PRIORITY dst ip=%s has priority of 1...." % packet.next.dstip)
                        #     msg.priority = 1

                        # event.connection.send(msg.pack())
                        event.connection.send(msg)

            elif isinstance(packet.next, arp):
                pktnext = packet.next

                if pktnext.prototype == arp.PROTO_TYPE_IP:
                    if pktnext.hwtype == arp.HW_TYPE_ETHERNET:
                        if pktnext.protosrc != 0:

                            # Learn or update port, mac info
                            self.forwardTable[dpid][pktnext.protosrc] = Entry(inport, packet.src)

                            # Send any waiting packets...
                            self._send_lost_buffers(dpid, pktnext.protosrc, packet.src, inport)

                            if pktnext.opcode == arp.REQUEST:
                                if pktnext.protodst in self.forwardTable[dpid]:
                                    # Reply ARP back
                                    r = arp()
                                    r.hwtype = pktnext.hwtype
                                    r.prototype = pktnext.prototype
                                    r.hwlen = pktnext.hwlen
                                    r.protolen = pktnext.protolen
                                    r.opcode = arp.REPLY
                                    r.hwdst = pktnext.hwsrc
                                    r.protodst = pktnext.protosrc
                                    r.protosrc = pktnext.protodst
                                    r.hwsrc = self.forwardTable[dpid][pktnext.protodst].mac
                                    e = ethernet(type=packet.type, src=dpid_to_mac(dpid), dst=pktnext.hwsrc)
                                    e.set_payload(r)
                                    log.debug("s=%i sp=%i answer ARP for %s" % (dpid, inport, str(r.protosrc)))
                                    msg = of.ofp_packet_out()
                                    msg.data = e.pack()
                                    msg.actions.append(of.ofp_action_output(port = of.OFPP_IN_PORT))
                                    msg.in_port = inport
                                    event.connection.send(msg)
                                    return

                log.debug("s=%i sp=%i FLOOD ARP %s %s => %s" % (dpid, inport, {arp.REQUEST:"request",arp.REPLY:"reply"}.get(pktnext.opcode, 'op:%i' % (pktnext.opcode,)), str(pktnext.protosrc), str(pktnext.protodst)))
                msg = of.ofp_packet_out(in_port = inport, data = event.ofp, action = of.ofp_action_output(port = of.OFPP_FLOOD))
                # msg.priority = priorityLearn
                event.connection.send(msg)



        # When it knows nothing about the destination, flood but don't install the rule
        def flood (message = None):
            """ Floods the packet """
            msg = of.ofp_packet_out()
            if time.time() - event.connection.connect_time >= _flood_delay:
                # Only flood if we've been connected for a little while...

                if self.hold_down_expired is False:
                    # Oh yes it is!
                    self.hold_down_expired = True
                    log.info("%s: Flood hold-down expired -- flooding",
                     dpid_to_str(event.dpid))

                if message is not None: log.debug(message)
                #log.debug("%i: flood %s -> %s", event.dpid,packet.src,packet.dst)
                # OFPP_FLOOD is optional; on some switches you may need to change
                # this to OFPP_ALL.
                msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
            else:
                pass
                #log.info("Holding down flood for %s", dpid_to_str(event.dpid))
            msg.data = event.ofp
            msg.in_port = event.port
            event.connection.send(msg)

        def drop (priorityLevel = 1):
            # drop (duration = None)
            """
            Drops this packet and optionally installs a flow to continue
            dropping similar ones for a while
            """
            log.debug("======= DROPPING PACKET =======")
            msg = of.ofp_packet_out()
            msg.buffer_id = event.ofp.buffer_id
            msg.in_port = event.port
            msg.actions.append(of.ofp_action_output(port=of.OFPP_NONE))
            msg.priority = priorityLevel
            event.connection.send(msg)

            # if duration is not None:
            #     if not isinstance(duration, tuple):
            #         duration = (duration,duration)
            #     msg = of.ofp_flow_mod()
            #     msg.match = of.ofp_match.from_packet(packet)
            #     msg.idle_timeout = duration[0]
            #     msg.hard_timeout = duration[1]
            #     msg.buffer_id = event.ofp.buffer_id
            #     event.connection.send(msg)
            # elif event.ofp.buffer_id is not None:
            #     msg = of.ofp_packet_out()
            #     msg.buffer_id = event.ofp.buffer_id
            #     msg.in_port = event.port
            #     msg.actions.append(of.ofp_action_output(port=of.OFPP_NONE))
            #     msg.priority = 1
            #     event.connection.send(msg)


        forward()


    def _handle_ConnectionUp(self, event):
        dpid = dpid_to_str(event.dpid)
        log.debug("Switch %s has come up.", dpid)

        self.read_Policy(self.policyFile)

    # Send the firewall policies to the switch
#    def sendFirewallPolicy(connection, policy):


#    for i in [FIREWALL POLICIES]:
#        sendFirewallPolicy(event.connection, i)


def launch(transparent=False, hold_down=_flood_delay, rule="policy.in"):
    # Run discovery and spanning tree modules
    pox.openflow.discovery.launch()
    pox.openflow.spanning_tree.launch()


    # Check the firewall file exists locally and not empty
    log.info("*** Firewall file : %s", (rule))
    if os.path.isfile(rule) == False:
         #log.debug("*** Firewall file %s not found!",(rule))
         raise RuntimeError(" Firewall rules %s not found!" % (rule))
    else:
         if os.stat(rule).st_size == 0:
             #raise RuntimeError(" Firewall rules %s empty!" % (rule))
             log.info("*** Warning: empty firewall rules!")

    log.info("*** Firewall file: %s found!" % (rule))

    # Starting the controller module
    core.registerNew(Controller, rule)
