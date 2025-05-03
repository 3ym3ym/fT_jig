Simple jig to measure fT parameter of NPN transistors. 
The idea is from Charles Wenzel : https://techlib.com/newprojects.htm . My twist on it is using fixed frequency rather than variable, and adjust the input amplitude instead, until the RF detector shows a fixed voltage in the middle of its working linear range, let's say 1V.
10MHz sine wave of variable amplitude is generated using PIO and R-2R DAC. See https://www.instructables.com/Arbitrary-Wave-Generator-With-the-Raspberry-Pi-Pic/ for details.
**Instructions:**
 - Install MicroPython on Raspberry Pi Pico. An easy way is to use Thonny.
 - Copy main.py to the Pico root directory. It will be executed on startup.
 - Assemble the jig on a protoyping board with a ground plane. If not available, use a regular prototyping board (not a solderless one. Make all connections that carry the RF signal very short. Use a lot of ground wires.
 - Optional: connect the SSD1306 128x64 OLED display to I2C pins if plan to use the device standalone (no computer). It will display the same info as printed in the Thonny shell window.

**Notes**
Works fot fT range of 80MHz to 400MHz. 
