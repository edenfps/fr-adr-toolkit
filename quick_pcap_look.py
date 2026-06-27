"""
Dump all packet headers to understand pcap structure.
"""
import struct

def read_pcap(filepath, max_packets=50):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    print(f"File size: {len(data)} bytes")
    
    # Pcap global header
    magic = struct.unpack_from('<I', data, 0)[0]
    print(f"Magic: 0x{magic:08X}")
    
    pos = 24
    packet_num = 0
    
    while pos < len(data) and packet_num < max_packets:
        if pos + 16 > len(data):
            break
        
        ts_sec = struct.unpack_from('<I', data, pos)[0]
        ts_usec = struct.unpack_from('<I', data, pos + 4)[0]
        incl_len = struct.unpack_from('<I', data, pos + 8)[0]
        orig_len = struct.unpack_from('<I', data, pos + 12)[0]
        
        pos += 16
        
        if pos + incl_len > len(data):
            print(f"  Packet {packet_num}: incl_len={incl_len} exceeds remaining data")
            break
        
        packet_data = data[pos:pos + incl_len]
        pos += incl_len
        packet_num += 1
        
        eth_offset = 0
        if len(packet_data) < 14:
            print(f"  Packet {packet_num}: too short ({len(packet_data)} bytes)")
            continue
        
        eth_type = struct.unpack_from('>H', packet_data, 12)[0]
        
        print(f"\nPacket {packet_num}: len={incl_len} eth_type=0x{eth_type:04X}")
        
        if eth_type == 0x0800 and len(packet_data) >= 34:
            # IPv4
            ip_offset = 14
            protocol = packet_data[ip_offset + 9]
            ihl = (packet_data[ip_offset] & 0x0F) * 4
            src_ip = '.'.join(str(b) for b in packet_data[ip_offset+12:ip_offset+16])
            dst_ip = '.'.join(str(b) for b in packet_data[ip_offset+16:ip_offset+20])
            
            print(f"  IPv4: src={src_ip} dst={dst_ip} proto={protocol} ihl={ihl}")
            
            if protocol == 6 and len(packet_data) >= ip_offset + ihl + 20:
                tcp_offset = ip_offset + ihl
                src_port = struct.unpack_from('>H', packet_data, tcp_offset)[0]
                dst_port = struct.unpack_from('>H', packet_data, tcp_offset + 2)[0]
                tcp_data_offset = ((packet_data[tcp_offset + 12] >> 4) & 0x0F) * 4
                payload_offset = tcp_offset + tcp_data_offset
                payload = packet_data[payload_offset:]
                
                print(f"  TCP: src_port={src_port} dst_port={dst_port} payload_len={len(payload)}")
                
                if len(payload) > 0:
                    # Check first bytes for SOE protocol patterns
                    hex_vals = payload[:min(32, len(payload))].hex(' ')
                    print(f"  Payload start: {hex_vals}")
                    
                    # Try different packet interpretations
                    if len(payload) >= 2:
                        # SOE packets often start with opcode byte
                        print(f"  Byte0=0x{payload[0]:02X} Byte1=0x{payload[1]:02X}")
                        
                        # Look for fishing opcode 0x8A anywhere
                        for i, b in enumerate(payload):
                            if b == 0x8A and i + 1 < len(payload) and payload[i+1] == 0x00:
                                print(f"  >>> FOUND FISHING OPCODE at offset {i}!")
                                print(f"      Context: {payload[max(0,i-4):i+20].hex(' ')}")

if __name__ == '__main__':
    read_pcap(r'c:\Users\bobya\FRController\packet logs\2014-03-25.pcap')
