from tildagonos import tildagonos
from machine import I2C
import struct
from machine import I2C

from system.hexpansion.util import *




BLS0 = (0x5a, 0, (1<<0))
BLS1 = (0x5a, 0, (1<<1))

LED = BLS0
WR = BLS1

tildagonos.system_i2c.writeto_mem(0x5a, 0x04, bytes([0xc8, 0xff]))
tildagonos.set_egpio_pin(LED, 0)
tildagonos.set_egpio_pin(WR, 0)

if False:
    # Set up i2c
    port = 2  # <<-- Customize!!
    i2c = I2C(port)

    # autodetect eeprom address
    addr = detect_eeprom_addr(i2c)
    print(f"Detected eeprom at {hex(addr)}")

    # Fill in your desired header info here:
    header = HexpansionHeader(
        manifest_version="2024",
        fs_offset=32,
        eeprom_page_size=32,
        eeprom_total_size=1024 * 8,
        vid=0xCA75,
        pid=0x1337,
        unique_id=0x0,
        friendly_name="GCHQ.NET",
    )

    # Write and read back header
    write_header(port, header, addr)
    header = read_hexpansion_header(i2c, addr)

    # Get block devices
    eep, partition = get_hexpansion_block_devices(i2c, header, addr)

    # Format
    vfs.VfsLfs2.mkfs(partition)

    # And mount!
    vfs.mount(partition, "/eeprom")



from scripts import mount_hexpansions