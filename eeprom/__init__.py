from app import App
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.hexpansion.events import HexpansionEvent
import asyncio, math, ujson, time, ubinascii, network, events
import requests as re
wlan=network.WLAN(network.WLAN.IF_STA)

class GCHQMarkerConnectEvent(HexpansionEvent):
    pass

class GCHQCaptureEvent(events.Event):
    def __init__(self):
        pass


class ATSHA204:
    CHECKMAC = 0x28
    DERIVEKEY = 0x1C
    DEVREV = 0x30
    GENDIG = 0x15
    HMAC = 0x11
    LOCK = 0x17
    MAC = 0x08
    NONCE = 0x16
    PAUSE = 0x01
    RANDOM = 0x1b
    READ = 0x02
    SHA = 0x47
    UPDATEEXTRA = 0x20
    WRITE = 0x12

    def __init__(self, i2c):
        self.i2c = i2c
        self.addr = 0x64
        
    @staticmethod
    def calc_crc(data):
        PRESET = 0x0000
        POLYNOMIAL = 0x8005 # bit reverse of 0x8005

        crc = PRESET
        for d in data:

            d = ((d & 0x55) << 1) | ((d & 0xAA) >> 1)
            d = ((d & 0x33) << 2) | ((d & 0xCC) >> 2)
            d = ((d & 0x0F) << 4) | ((d & 0xF0) >> 4)

            crc ^= d << 8
            for j in range(0, 8):
                if (crc & 0x8000) > 0:
                    crc = (crc << 1) ^ POLYNOMIAL
                else:
                    crc = crc << 1

        return crc.to_bytes(2, 'little')

    def wakeup(self):
        try:
            self.i2c.writeto(self.addr, bytes())
        except:
            pass
        time.sleep(.001)

    def send_command(self, opcode, param1, param2, data = bytes()):
        assert(len(param1) == 1)
        assert(len(param2) == 2)
        count = len(data) + 7 # count includes: count, opcode, param1, param2(2), crc(2)
        tx_data = bytes([count, opcode]) + param1 + param2 + data
        crc = self.calc_crc(tx_data)
        tx_data = b'\x03' + tx_data + crc
        self.wakeup()
        self.i2c.writeto(self.addr, tx_data)

    def read_response(self, nbytes):
        nbytes += 3
        resp_data = self.i2c.readfrom(self.addr, nbytes)
        crc = resp_data[:-2]
        calcd_crc = self.calc_crc(resp_data[:2])
        if resp_data[0] == 4 and crc == calcd_crc:
            return resp_data[1]
        return resp_data[1:-2]
    
    def SerNo(self):
        param1 = bytes([0x80])
        param2 = bytes(2)
        self.send_command(self.READ, param1, param2)
        time.sleep(.004)
        resp = self.read_response(32)
        print(resp)
        sn = resp[0:4] + resp[8:13]
        return sn
    
    def Random(self, mode = 1):
        param1 = mode.to_bytes(1, 'little')
        param2 = bytes(2)
        self.send_command(self.RANDOM, param1, param2)
        time.sleep(.050)
        resp = self.read_response(32)
        return resp
    
    def Mac(self, mode, slotId, challenge = bytes()):
        assert(len(challenge) in [0, 32])
        assert(mode&1 == (len(challenge) == 0))
        param1 = mode.to_bytes(1, 'little')
        param2 = slotId.to_bytes(2, 'little')
        self.send_command(self.MAC, param1, param2, challenge)
        time.sleep(.035)
        resp = self.read_response(32)
        return resp
    
    def Nonce(self, mode, data):
        assert(len(data) in [20, 32])
        assert(mode&2 == (len(data)==32))
        param1 = mode.to_bytes(1, 'little')
        param2 = bytes(2)
        self.send_command(self.NONCE, param1, param2, data)
        time.sleep(.060)
        resp = self.read_response(1 if mode == 3 else 32)
        return resp
        
def get_device_mac():
    return "-".join([f"{b:02X}" for b in  wlan.config('mac')])


def perform_capture(atsha):
    sn = atsha.SerNo()
    nonce = atsha.Nonce(0x01, bytes(get_device_mac(), 'ascii') + bytes(20-17))
    mac = atsha.Mac(0x01, 0)
    return int.from_bytes(sn, 'little'), ubinascii.hexlify(nonce), ubinascii.hexlify(mac)

_captures = None
_capfile = "/gchq.net.json"

def save_captures():
    with open(_capfile, 'w') as f:
        ujson.dump(_captures, f)
    
def load_captures():
    global _captures
    try:
        with open(_capfile, 'r') as f:
            _captures = ujson.load(f)
    except:
        _captures = []
        save_captures()
    if _captures is None:
        _captures = []

def save_capture(capture):
    global _captures
    load_captures()
    _captures.append(capture)
    save_captures()
        
        
def roundtext(ctx, t, r, top=False, h=20):
    ctx.save()
    r=(h-r) if top else r
    w=sum(map(ctx.text_width, t))
    ctx.rotate(w/2/r)
    for c in t:
        w=ctx.text_width(c)
        ctx.rotate(-w/2/r)
        
        ctx.move_to(-w/2, r)
        ctx.text(c)
        ctx.move_to(0,0)
        ctx.rotate(-w/2/r)
    ctx.restore()
    

class GCHQMarkerApp(App):
    def __init__(self, config=None):
        self.port = config
        self.animation_counter = 0
        self.atsha = ATSHA204(config.i2c)
        self.has_app = False
        self.message = "Capturing!"
        self.top_message = "DO NOT EJECT"
        
    async def background_task(self):
        
        eventbus.emit(RequestForegroundPushEvent(self))
        
        try:
            import apps.gchq_net
            self.has_app = True
        except:
            self.state = "missing installed app"
            print("missing main app")
        capture = perform_capture(self.atsha)
        print(capture)
        save_capture(capture)
        self.message = "Capture Saved"
        self.top_message = "SAFE TO EJECT"
        print(self.message)
        
        while True:
            await asyncio.sleep(3)
            self.message = "Open companion app"
            await asyncio.sleep(3)
            self.message = "gchq.net/play"
            
    def update(self, delta):
        self.animation_counter += delta/1000
        pass
    
    def draw(self, ctx):
        self.draw_logo_animated(ctx)

    def draw_logo_animated(self, ctx):
        legw = .12
        ctx.arc(0,0,150,0,2*math.pi,1)
        ctx.rgba(0, 0, 0, 1)
        ctx.fill()
        ctx.arc(0, 0, 100, 0, 2*math.pi, 0)
        ctx.rgba(1, 1, 1, 1)
        ctx.fill()
        ctx.arc(0, 0, 75, 0, 2*math.pi, 0)
        ctx.rgba(0,0,0, 1)
        ctx.fill()
        ctx.save()
        ctx.rotate(self.animation_counter * math.pi / 3)
        for i in range(3):
            ctx.begin_path()
            ctx.arc(0, 0, 105, i*math.pi*2/3, (i+legw)*math.pi*2/3, 0)
            ctx.arc(0, 0, 44, (i+legw)*math.pi*2/3, i*math.pi*2/3, -1)
            ctx.rgba(1, 1, 1, 1)
            ctx.fill()
        ctx.restore()
            
        ctx.arc(0, 0, 45, 0, 2*math.pi, 0)
        ctx.rgba(1, 1, 1, 1)
        ctx.fill()
            
        ctx.arc(0, 0, 40, 0, 2*math.pi, 0)
        ctx.rgba(0,0,0, 1)
        ctx.fill()

        ps = [(-30, 5), (-20, 14), (-12, 5), (-5, 5), (5, 10), (12, 10), (20, 6)]

        ctx.move_to(ps[0][0], ps[0][1])
        ctx.begin_path()
        for px, py in ps:
            ctx.line_to(px, py)
        for px, py in ps:
            ctx.line_to(-px, -py)
        
        ctx.line_to(-30, 5)

        ctx.rgba(1, 1, 1, 1)
        ctx.fill()
        
        
        ctx.rgba(0,0,0,1)
        
        roundtext(ctx,self.message, 97, False)
        roundtext(ctx,self.top_message, 97, True)

        

__app_export__ = GCHQMarkerApp


