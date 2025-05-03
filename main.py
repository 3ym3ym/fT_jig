# Arbitrary waveform generator for Rasberry Pi Pico
# Requires 8-bit R2R DAC on pins 0-7. Works for R=1kOhm
# Achieves 125Msps when running 125MHz clock
# Rolf Oldeman, 13/2/2021. CC BY-NC-SA 4.0 licence
# tested with rp2-pico-20210205-unstable-v1.14-8-g1f800cac3.uf2
from machine import Pin,mem32,ADC,I2C
from rp2 import PIO, StateMachine, asm_pio
from array import array
from utime import sleep
from math import pi,sin,exp,sqrt,floor
from uctypes import addressof
from random import random
import ssd1306


fclock=125000000 #clock frequency of the pico
adc = ADC(Pin(27))

i2c = I2C(0, scl=Pin(17), sda=Pin(16), freq=400000)
oled_width = 128
oled_height = 64
oled = ssd1306.SSD1306_I2C(oled_width, oled_height, i2c)
oled.fill(0)
oled.show()


DMA_BASE=0x50000000
CH0_READ_ADDR  =DMA_BASE+0x000
CH0_WRITE_ADDR =DMA_BASE+0x004
CH0_TRANS_COUNT=DMA_BASE+0x008
CH0_CTRL_TRIG  =DMA_BASE+0x00c
CH0_AL1_CTRL   =DMA_BASE+0x010
CH1_READ_ADDR  =DMA_BASE+0x040
CH1_WRITE_ADDR =DMA_BASE+0x044
CH1_TRANS_COUNT=DMA_BASE+0x048
CH1_CTRL_TRIG  =DMA_BASE+0x04c
CH1_AL1_CTRL   =DMA_BASE+0x050

PIO0_BASE      =0x50200000
PIO0_TXF0      =PIO0_BASE+0x10
PIO0_SM0_CLKDIV=PIO0_BASE+0xc8

#state machine that just pushes bytes to the pins
@asm_pio(out_init=(PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH),
         out_shiftdir=PIO.SHIFT_RIGHT, autopull=True, pull_thresh=32)
def stream():
    out(pins,8)

sm = StateMachine(0, stream, freq=125000000, out_base=Pin(0))
sm.active(1)

#2-channel chained DMA. channel 0 does the transfer, channel 1 reconfigures
p=array('I',[0]) #global 1-element array
def startDMA(ar,nword):
    #first disable the DMAs to prevent corruption while writing
    mem32[CH0_AL1_CTRL]=0
    mem32[CH1_AL1_CTRL]=0
#setup first DMA which does the actual transfer
    mem32[CH0_READ_ADDR]=addressof(ar)
    mem32[CH0_WRITE_ADDR]=PIO0_TXF0
    mem32[CH0_TRANS_COUNT]=nword
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x00 #wait for PIO0_TX0
    CHAIN_TO=1    #start channel 1 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #for write to array
    INCR_READ=1   #for read from array
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL0=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH0_AL1_CTRL]=CTRL0

#setup second DMA which reconfigures the first channel
    p[0]=addressof(ar)
    mem32[CH1_READ_ADDR]=addressof(p)
    mem32[CH1_WRITE_ADDR]=CH0_READ_ADDR
    mem32[CH1_TRANS_COUNT]=1
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x3f #no pacing
    CHAIN_TO=0    #start channel 0 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #single write
    INCR_READ=0   #single read
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL1=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH1_CTRL_TRIG]=CTRL1



def setupwave(buf,f,w):
    div=fclock/(f*maxnsamp) # required clock division for maximum buffer size
    if div<1.0:  #can't speed up clock, duplicate wave instead
        dup=int(1.0/div)
        nsamp=int((maxnsamp*div*dup+0.5)/4)*4 #force multiple of 4
        clkdiv=1
    else:        #stick with integer clock division only
        clkdiv=int(div)+1
        nsamp=int((maxnsamp*div/clkdiv+0.5)/4)*4 #force multiple of 4
        dup=1

    #fill the buffer
    for isamp in range(nsamp):
        buf[isamp]=max(0,min(255,int(256*eval(w,dup*(isamp+0.5)/nsamp))))

    #set the clock divider
    clkdiv_int=min(clkdiv,65535) 
    clkdiv_frac=0 #fractional clock division results in jitter
    mem32[PIO0_SM0_CLKDIV]=(clkdiv_int<<16)|(clkdiv_frac<<8)

    #start DMA
    startDMA(buf,int(nsamp/4))


#evaluate the content of a wave
def eval(w,x):
    m,s,p=1.0,0.0,0.0
    if 'phasemod' in w.__dict__:
        p=eval(w.phasemod,x)
    if 'mult' in w.__dict__:
        m=eval(w.mult,x)
    if 'sum' in w.__dict__:
        s=eval(w.sum,x)
    x=x*w.replicate-w.phase-p
    x=x-floor(x)  #reduce x to 0.0-1.0 range
    v=w.func(x,w.pars)
    v=v*w.amplitude*m
    v=v+w.offset+s
    return v

#some common waveforms. combine with sum,mult,phasemod
def sine(x,pars):
    return sin(x*2*pi)
    

#make buffers for the waveform.
#large buffers give better results but are slower to fill
maxnsamp=1024 #must be a multiple of 4. miximum size is 65536
wavbuf={}
wavbuf[0]=bytearray(maxnsamp)
wavbuf[1]=bytearray(maxnsamp)
ibuf=0

#empty class just to attach properties to
class wave:
    pass

while True :
    ampl = 0.05
    for m in range(8) :
        wave1=wave()
        wave1.amplitude=ampl
        wave1.offset=0.5
        wave1.phase=0.0
        wave1.replicate=1
        wave1.func=sine
        wave1.pars=[]

        freq = 1e7
        setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
        v=0
        for i in range(10) :
            v += adc.read_u16()
            sleep(0.01)
        vout = v*3.3/(10*65536)
        print(m,ampl,vout)
        
        oled.fill(0)
        val_str = '{} {} {}'.format(m,ampl,vout)
        oled.text(val_str, 0, 0)
        oled.show()
        
        sar_factor = 1+1.0/2**m
        if (vout<1.0) :
            print("mul by ", sar_factor)
            ampl = ampl * sar_factor
        else :
            print("div by",sar_factor)
            ampl = ampl / sar_factor

    oled.fill(0)
    val_str = 'fT = {:.0f}MHz'.format(freq*4.2e-6/ampl)
    oled.text(val_str, 0, 10)
    oled.show()
    
    print ("fT = ", freq*4.2e-6/ampl)
    sleep(1)

#step through amplitudes
#freq=2e5
#for amp in (0.1,0.2,0.3,0.4,0.5):
#    wave1.amplitude=amp
#    setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2

