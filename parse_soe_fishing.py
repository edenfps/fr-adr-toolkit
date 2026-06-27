"""
Search raw pcap bytes for 0x8A (fishing opcode) in any context.
Also dump ALL SOE opcodes seen to understand protocol format.
"""
import struct

def analyze_pcap(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    print(f"File: {filepath}")
    print(f"Size: {len(data)} bytes")
    
    # Search for 0x8A 0x00 anywhere
    count_8a00 = 0
    for i in range(len(data) - 1):
        if data[i] == 0x8A and data[i+1] == 0x00:
            count_8a00 += 1
            if count_8a00 <= 10:
                ctx = data[max(0,i-8):min(len(data),i+24)]
                print(f"\n  Found 0x8A 0x00 at file offset 0x{i:08X}")
                print(f"  Context: {ctx.hex(' ')}")
    print(f"\nTotal 0x8A00 occurrences: {count_8a00}")
    
    # Now parse SOE packets and dump opcodes
    pos = 24
    packet_num = 0
    opcode_counts = {}
    tunneled_opcodes = {}
    
    while pos < len(data) and packet_num < 10000:
        if pos + 16 > len(data):
            break
        
        incl_len = struct.unpack_from('<I', data, pos + 8)[0]
        pos += 16
        
        if pos + incl_len > len(data):
            break
        
        packet_data = data[pos:pos + incl_len]
        pos += incl_len
        packet_num += 1
        
        if len(packet_data) < 42:
            continue
        
        eth_type = struct.unpack_from('>H', packet_data, 12)[0]
        if eth_type != 0x0800:
            continue
        
        ip_offset = 14
        protocol = packet_data[ip_offset + 9]
        if protocol != 17:
            continue
        
        ihl = (packet_data[ip_offset] & 0x0F) * 4
        udp_offset = ip_offset + ihl
        udp_len = struct.unpack_from('>H', packet_data, udp_offset + 4)[0]
        payload_offset = udp_offset + 8
        payload = packet_data[payload_offset:payload_offset + udp_len - 8]
        
        if len(payload) < 4:
            continue
        
        soe_pos = 0
        while soe_pos + 4 <= len(payload):
            soe_len = struct.unpack_from('>H', payload, soe_pos)[0]
            soe_opcode = struct.unpack_from('>H', payload, soe_pos + 2)[0]
            
            if soe_len == 0 or soe_pos + soe_len > len(payload):
                break
            
            soe_data = payload[soe_pos + 4:soe_pos + soe_len]
            
            # Count SOE opcodes
            if soe_opcode not in opcode_counts:
                opcode_counts[soe_opcode] = 0
            opcode_counts[soe_opcode] += 1
            
            # If this is a tunneled packet, look at the inner opcode
            if len(soe_data) >= 2:
                inner_opcode = struct.unpack_from('<H', soe_data, 0)[0]
                if inner_opcode not in tunneled_opcodes:
                    tunneled_opcodes[inner_opcode] = 0
                tunneled_opcodes[inner_opcode] += 1
                
                # Print fishing-related ones (138)
                if inner_opcode == 138:
                    sub_op = 0
                    if len(soe_data) >= 4:
                        sub_op = struct.unpack_from('<H', soe_data, 2)[0]
                    print(f"\n  FISHING: SOE op=0x{soe_opcode:04X} inner=138 sub={sub_op}")
                    print(f"  Data: {soe_data[:40].hex(' ')}")
            
            soe_pos += soe_len
    
    print(f"\n\nSOE Opcodes seen ({len(opcode_counts)} unique):")
    for opcode, count in sorted(opcode_counts.items()):
        print(f"  0x{opcode:04X} ({opcode}): {count}")
    
    print(f"\nTunneled inner opcodes ({len(tunneled_opcodes)} unique):")
    for opcode, count in sorted(tunneled_opcodes.items()):
        marker = " <-- FISHING!" if opcode == 138 else ""
        print(f"  {opcode} (0x{opcode:04X}): {count}{marker}")

if __name__ == '__main__':
    analyze_pcap(r'c:\Users\bobya\FRController\packet logs\2014-03-25.pcap')
