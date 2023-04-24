# The program implements a simple controller for a network with 6 hosts and 5 switches. The switches are connected in
# a diamond topology (without vertical links): - 3 hosts are connected to the left (s1) and 3 to the right (s5) edge
# of the diamond. Overall operation of the controller: - default routing is set in all switches on the reception of
# packet_in messages form the switch, - then the routing for (h1-h4) pair in switch s1 is changed every one second in
# a round-robin manner to load balance the traffic through switches s3, s4, s2.

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpidToStr
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.packet.arp import arp
from pox.lib.packet.ethernet import ethernet, ETHER_BROADCAST
from pox.lib.packet.packet_base import packet_base
from pox.lib.packet.packet_utils import *
import pox.lib.packet as pkt
from pox.lib.recoco import Timer
import time
import struct

log = core.getLogger()

s1_dpid = 0
s2_dpid = 0
s3_dpid = 0
s4_dpid = 0
s5_dpid = 0

s1_p1 = 0
s1_p4 = 0
s1_p5 = 0
s1_p6 = 0
s2_p1 = 0
s3_p1 = 0
s4_p1 = 0

pre_s1_p1 = 0
pre_s1_p4 = 0
pre_s1_p5 = 0
pre_s1_p6 = 0
pre_s2_p1 = 0
pre_s3_p1 = 0
pre_s4_p1 = 0

start_time = 0.0
sent_time1 = 0.0
sent_time2 = 0.0
sent_time3 = 0.0
sent_time4 = 0.0
received_time1 = 0.0
received_time2 = 0.0
mytimer = 0
OWD1 = 0.0
OWD2 = 0.0
OWD3 = 0.0
OWD4 = 0.0
delay12 = 0.0
delay13 = 0.0
delay14 = 0.0

turn = 0


class myproto(packet_base):
    def __init__(self):
        packet_base.__init__(self)
        self.timestamp = 0

    def hdr(self, payload):
        # print self.timestamp
        return struct.pack('!Q', self.timestamp)


class SwitchInfo:
    s1_port = 0
    num_flows = 0
    delay = 0
    packets_queue = [0]*10

    def __init__(self, new_s1_port):
        self.s1_port = new_s1_port

    def update_traffic(self, new_packets):
        for i in range(1, 10):
            self.packets_queue[i-1] = self.packets_queue[i]
        self.packets_queue[9] = new_packets

        self.num_flows = 0
        for i in range(0, 10):
            self.num_flows = self.num_flows + self.packets_queue[i]


class SwitchInfoList:
    switch_infos = [SwitchInfo(4), SwitchInfo(5), SwitchInfo(6)]

    def sort_by_flows(self):
        def get_flows(e):
            return e.num_flows

        self.switch_infos.sort(key=get_flows)
        print("ports by flows:")
        for i in range(0, 3):
            print("p" + str(self.switch_infos[i].s1_port) + ": " + str(self.switch_infos[i].num_flows))

    def get_info_for_port(self, s1_port):
        for k in range(3):
            if self.switch_infos[k].s1_port == s1_port:
                return self.switch_infos[k]
        return self.switch_infos[0]


class Intent:
    source = 0  # 1 for h1, 2 for h2, 3 for h3
    destination = 0  # 4 for h4, 5 for h5, 6 for h6
    max_delay = 0

    def __init__(self, new_source, new_destination, new_delay):
        self.source = new_source
        self.destination = new_destination
        self.max_delay = new_delay

    def print_self(self):
        print("Intent: max delay from h{} to h{} must not exceed {}".format(self.source, self.destination,
                                                                            self.max_delay))


TheSwitchInfoList = SwitchInfoList()
active_intents = []


def print_intents():
    for intent in active_intents:
        intent.print_self()


def _timer_func():
    global start_time, sent_time1, sent_time2, sent_time3, sent_time4, s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid, turn

    if s1_dpid != 0 and not core.openflow.getConnection(s1_dpid) is None:
        core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        sent_time1 = time.time() * 1000 * 10 - start_time  # T1

        f = myproto()
        e = pkt.ethernet()  # create L2 type packet (frame) object
        e.src = EthAddr("0:0:0:0:0:2")  # DO ZMIANY
        e.dst = EthAddr("0:1:0:0:0:1")
        e.type = 0x5577
        msg1 = of.ofp_packet_out()  # create PACKET_OUT message object
        msg1.actions.append(of.ofp_action_output(port=4))  # set the output port for the packet in switch0
        msg2 = of.ofp_packet_out()
        msg2.actions.append(of.ofp_action_output(port=5))
        msg3 = of.ofp_packet_out()
        msg3.actions.append(of.ofp_action_output(port=6))
        f.timestamp = int(time.time() * 1000 * 10 - start_time)  # set the timestamp in the probe packet
        e.payload = f
        msg1.data = e.pack()
        msg2.data = e.pack()
        msg3.data = e.pack()
        core.openflow.getConnection(s1_dpid).send(msg1)
        core.openflow.getConnection(s1_dpid).send(msg2)
        core.openflow.getConnection(s1_dpid).send(msg3)
        print("=====> probe sent: f=", f.timestamp, " after=", int(time.time() * 1000 * 10 - start_time), " [10*ms]")

    if s2_dpid != 0 and not core.openflow.getConnection(s2_dpid) is None:
        core.openflow.getConnection(s2_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        sent_time2 = time.time() * 1000 * 10 - start_time  # T2_S2

    if s3_dpid != 0 and not core.openflow.getConnection(s3_dpid) is None:
        core.openflow.getConnection(s3_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        sent_time3 = time.time() * 1000 * 10 - start_time  # T2_S3

    if s4_dpid != 0 and not core.openflow.getConnection(s4_dpid) is None:
        core.openflow.getConnection(s4_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        sent_time4 = time.time() * 1000 * 10 - start_time  # T2_S4


def getTheTime():  # function to create a timestamp
    flock = time.localtime()
    then = "[%s-%s-%s" % (str(flock.tm_year), str(flock.tm_mon), str(flock.tm_mday))

    if int(flock.tm_hour) < 10:
        hrs = "0%s" % (str(flock.tm_hour))
    else:
        hrs = str(flock.tm_hour)
    if int(flock.tm_min) < 10:
        mins = "0%s" % (str(flock.tm_min))
    else:
        mins = str(flock.tm_min)

    if int(flock.tm_sec) < 10:
        secs = "0%s" % (str(flock.tm_sec))
    else:
        secs = str(flock.tm_sec)

    then += "]%s.%s.%s" % (hrs, mins, secs)
    return then


def _handle_portstats_received(event):
    # Observe the handling of port statistics provided by this function.

    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
    global s1_p1, s1_p4, s1_p5, s1_p6, s2_p1, s3_p1, s4_p1
    global pre_s1_p1, pre_s1_p4, pre_s1_p5, pre_s1_p6, pre_s2_p1, pre_s3_p1, pre_s4_p1
    global OWD1, OWD2, OWD3, OWD4

    received_time = time.time() * 1000 * 10 - start_time

    if event.connection.dpid == s1_dpid:  # The DPID of one of the switches involved in the link
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s1_p1 = s1_p1
                    s1_p1 = f.rx_packets
                    # print "s1_p1->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
                if f.port_no == 4:
                    pre_s1_p4 = s1_p4
                    s1_p4 = f.tx_packets
                    # s1_p4=f.tx_bytes
                    # print "s1_p4->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
                if f.port_no == 5:
                    pre_s1_p5 = s1_p5
                    s1_p5 = f.tx_packets
                if f.port_no == 6:
                    pre_s1_p6 = s1_p6
                    s1_p6 = f.tx_packets

        OWD1 = 0.5 * (received_time - sent_time1)
        # print "OWD1: ", OWD1, "ms"

    if event.connection.dpid == s2_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s2_p1 = s2_p1
                    s2_p1 = f.rx_packets
                    # s2_p1=f.rx_bytes
        print(getTheTime(), "s1_p4(Sent):", (s1_p4 - pre_s1_p4), "s2_p1(Received):", (s2_p1 - pre_s2_p1))
        TheSwitchInfoList.get_info_for_port(4).update_traffic(s1_p4 - pre_s1_p4)

        OWD2 = 0.5 * (received_time - sent_time2)
        # print "OWD2: ", OWD2, "ms"

    if event.connection.dpid == s3_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s3_p1 = s3_p1
                    s3_p1 = f.rx_packets
        print(getTheTime(), "s1_p5(Sent):", (s1_p5 - pre_s1_p5), "s3_p1(Received):", (s3_p1 - pre_s3_p1))
        TheSwitchInfoList.get_info_for_port(5).update_traffic(s1_p5 - pre_s1_p5)

        OWD3 = 0.5 * (received_time - sent_time3)
        # print "OWD3: ", OWD3, "ms"

    if event.connection.dpid == s4_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s4_p1 = s4_p1
                    s4_p1 = f.rx_packets
        print(getTheTime(), "s1_p6(Sent):", (s1_p6 - pre_s1_p6), "s4_p1(Received):", (s4_p1 - pre_s4_p1))
        TheSwitchInfoList.get_info_for_port(6).update_traffic(s1_p6 - pre_s1_p6)

        OWD4 = 0.5 * (received_time - sent_time4)
        # print "OWD4: ", OWD4, "ms"


def _handle_ConnectionUp(event):
    # waits for connections from all switches, after connecting to all of them it starts a round robin timer for triggering h1-h4 routing changes
    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid, mytimer
    print("ConnectionUp: ", dpidToStr(event.connection.dpid))

    # remember the connection dpid for the switch
    for m in event.connection.features.ports:
        if m.name == "s1-eth1":
            # s1_dpid: the DPID (datapath ID) of switch s1;
            s1_dpid = event.connection.dpid
            print("s1_dpid=", s1_dpid)
        elif m.name == "s2-eth1":
            s2_dpid = event.connection.dpid
            print("s2_dpid=", s2_dpid)
        elif m.name == "s3-eth1":
            s3_dpid = event.connection.dpid
            print("s3_dpid=", s3_dpid)
        elif m.name == "s4-eth1":
            s4_dpid = event.connection.dpid
            print("s4_dpid=", s4_dpid)
        elif m.name == "s5-eth1":
            s5_dpid = event.connection.dpid
            print("s5_dpid=", s5_dpid)

    if s1_dpid != 0 and s2_dpid != 0 and s3_dpid != 0 and s4_dpid != 0 and s5_dpid != 0:
        print("timer_func started.")
        mytimer = Timer(5, _timer_func, recurring=True)


def _handle_PacketIn(event):
    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid, active_intents, delay12, delay13, delay14

    received_time = time.time() * 1000 * 10 - start_time
    packet = event.parsed
    # print "_handle_PacketIn is called, packet.type:", packet.type, " event.connection.dpid:", event.connection.dpid

    # Below, set the default/initial routing rules for all switches and ports.
    # All rules are set up in a given switch on packet_in event received from the switch which means no flow entry has been found in the flow table.
    # This setting up may happen either at the very first pactet being sent or after flow entry expirationn inn the switch

    if event.connection.dpid == s1_dpid:
        # print "s1 connection up"
        handle_s1(event, packet)

    if event.connection.dpid == s2_dpid:
        # print "s2 connection up"
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806  # rule for ARP packets (x0806)
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        if packet.type == 0x5577:
            c = packet.find('ethernet').payload
            d, = struct.unpack('!Q', c)  # delay12
            delay12 = int(received_time - d - OWD1 - OWD2) / 10
            print("DELAY_12=", delay12, "[ms]", ", d=", d, ", OWD1=", int(OWD1), ", OWD2=", int(OWD2))
            for k in range(3):
                if SwitchInfoList.switch_infos[k].s1_port == 4:
                    SwitchInfoList.switch_infos[k].delay = delay12
            # with open("delay_values.txt", "w") as f:
            #    f.write(str(delay12))

    elif event.connection.dpid == s3_dpid:
        # print "s3 connection up"
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        if packet.type == 0x5577:
            c = packet.find('ethernet').payload
            d, = struct.unpack('!Q', c)
            delay13 = int(received_time - d - OWD1 - OWD3) / 10
            print("DELAY_13=", delay13, "[ms]", ", d=", d, ", OWD1=", int(OWD1), ", OWD3=", int(OWD3))
            for k in range(3):
                if SwitchInfoList.switch_infos[k].s1_port == 5:
                    SwitchInfoList.switch_infos[k].delay = delay13

    elif event.connection.dpid == s4_dpid:
        # print "s4 connection up"
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        if packet.type == 0x5577:
            c = packet.find('ethernet').payload
            d, = struct.unpack('!Q', c)
            delay14 = int(received_time - d - OWD1 - OWD4) / 10
            print("DELAY_14=", delay14, "[ms]", ", d=", d, ", OWD1=", int(OWD1), ", OWD4=", int(OWD4))
            for k in range(3):
                if SwitchInfoList.switch_infos[k].s1_port == 6:
                    SwitchInfoList.switch_infos[k].delay = delay14

    elif event.connection.dpid == s5_dpid:
        a = packet.find('arp')
        if a and a.protodst == "10.0.0.4":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=4))
            event.connection.send(msg)
        if a and a.protodst == "10.0.0.5":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=5))
            event.connection.send(msg)
        if a and a.protodst == "10.0.0.6":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=6))
            event.connection.send(msg)
        if a and a.protodst == "10.0.0.1":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=1))
            event.connection.send(msg)
        if a and a.protodst == "10.0.0.2":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=2))
            event.connection.send(msg)
        if a and a.protodst == "10.0.0.3":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=3))
            event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.1"
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 6
        msg.actions.append(of.ofp_action_output(port=3))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.1"
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.2"
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.3"
        msg.actions.append(of.ofp_action_output(port=3))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.4"
        msg.actions.append(of.ofp_action_output(port=4))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.5"
        msg.actions.append(of.ofp_action_output(port=5))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.6"
        msg.actions.append(of.ofp_action_output(port=6))
        event.connection.send(msg)


def satisfies_intents(src_host, dest_host, delay):
    for intent in active_intents:
        if intent.source == src_host and intent.destination == dest_host:
            if delay > intent.max_delay:
                return False
    return True


def handle_s1(event, packet):
    handle_s1_arp(event, packet)

    direct_flow(event, "10.0.0.1", 1)
    direct_flow(event, "10.0.0.2", 2)
    direct_flow(event, "10.0.0.3", 3)

    src_host = event.port
    if src_host == 1 or src_host == 2 or src_host == 3:
        UpdateIntent()
        for dest_host in [4, 5, 6]:
            TheSwitchInfoList.sort_by_flows()
            out_port = TheSwitchInfoList.switch_infos[0].s1_port
            for i in range(0, len(TheSwitchInfoList.switch_infos)):
                port_delay = TheSwitchInfoList.switch_infos[i].delay
                if satisfies_intents(src_host, dest_host, port_delay):
                    out_port = TheSwitchInfoList.switch_infos[i].s1_port
                    break

            direct_flow_by_source(event, src_host, dest_host, out_port)

    else:
        direct_flow(event, "10.0.0.4", 4)
        direct_flow(event, "10.0.0.5", 5)
        direct_flow(event, "10.0.0.6", 6)


def direct_flow_by_source(event, src_host, dest_host, out_port):
    print("directing flow from h" + str(src_host) + " to h" + str(dest_host) + " via " + str(out_port))
    dest_string = "10.0.0." + str(dest_host)
    msg = of.ofp_flow_mod()
    # msg.command = of.OFPFC_MODIFY_STRICT
    msg.priority = 200
    msg.idle_timeout = 0
    msg.hard_timeout = 0
    msg.match.dl_type = 0x0800
    msg.match.in_port = src_host
    msg.match.nw_dst = dest_string
    msg.actions.append(of.ofp_action_output(port=out_port))
    core.openflow.getConnection(s1_dpid).send(msg)
    # arp_lookup[dest_string] = out_port


def direct_flow(event, dest_address, out_port):
    msg = of.ofp_flow_mod()
    msg.priority = 100
    msg.idle_timeout = 0
    msg.hard_timeout = 0
    msg.match.dl_type = 0x0800
    msg.match.nw_dst = dest_address
    msg.actions.append(of.ofp_action_output(port=out_port))
    core.openflow.getConnection(s1_dpid).send(msg)
    # arp_lookup[dest_address] = out_port


arp_lookup = {
    "10.0.0.1": 1,
    "10.0.0.2": 2,
    "10.0.0.3": 3,
    "10.0.0.4": 4,
    "10.0.0.5": 5,
    "10.0.0.6": 6
}


def handle_s1_arp(event, packet):
    a = packet.find('arp')

    if a and a.protodst == "10.0.0.4":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.4"]))
        event.connection.send(msg)
    if a and a.protodst == "10.0.0.5":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.5"]))
        event.connection.send(msg)
    if a and a.protodst == "10.0.0.6":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.6"]))
        event.connection.send(msg)
    if a and a.protodst == "10.0.0.1":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.1"]))
        event.connection.send(msg)
    if a and a.protodst == "10.0.0.2":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.2"]))
        event.connection.send(msg)
    if a and a.protodst == "10.0.0.3":
        msg = of.ofp_packet_out(data=event.ofp)
        msg.actions.append(of.ofp_action_output(port=arp_lookup["10.0.0.3"]))
        event.connection.send(msg)


def UpdateIntent():
    global active_intents
    print("reading intent file!")
    # try:
    if True:
        f = open("intent.txt", "r")
        lines = f.readlines()
        active_intents = []
        for line in lines:
            arguments = line.split()
            source_host = int(arguments[0])
            destination_host = int(arguments[1])
            max_delay = int(arguments[2])
            active_intents.append(Intent(source_host, destination_host, max_delay))
        f.close()
        print_intents()
    # except:
    # print("failed to read intent file")


# As usually, launch() is the function called by POX to initialize the component (routing_controller.py in our case)
# indicated by a parameter provided to pox.py

def launch():
    global start_time
    print("siema!!!")
    # core is an instance of class POXCore (EventMixin) and it can register objects.
    # An object with name xxx can be registered to core instance which makes this object become a "component" available as pox.core.core.xxx.
    # for examples see e.g. https://noxrepo.github.io/pox-doc/html/#the-openflow-nexus-core-openflow
    core.openflow.addListenerByName("PortStatsReceived",
                                    _handle_portstats_received)  # listen for port stats , https://noxrepo.github.io/pox-doc/html/#statistics-events
    core.openflow.addListenerByName("ConnectionUp",
                                    _handle_ConnectionUp)  # listen for the establishment of a new control channel with a switch, https://noxrepo.github.io/pox-doc/html/#connectionup
    core.openflow.addListenerByName("PacketIn",
                                    _handle_PacketIn)  # listen for the reception of packet_in message from switch, https://noxrepo.github.io/pox-doc/html/#packetin
