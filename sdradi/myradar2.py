import time
import os
from time import sleep
import adi
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from timeit import default_timer as timer
import phaser.mycn0566 as mycn0566
CN0566=mycn0566.CN0566

from myad9361class import SDR

# Read back properties from hardware https://analogdevicesinc.github.io/pyadi-iio/devices/adi.ad936x.html
def printSDRproperties(sdr):
    print("Bandwidth of TX path:", sdr.tx_rf_bandwidth) #Bandwidth of front-end analog filter of TX path
    print("Loopback:", sdr.loopback) #0: disable, 1: Digital TX → Digital RX, 2: RF RX → RF TX
    print("TX gain chan0:", sdr.tx_hardwaregain_chan0) #Attenuation applied to TX path, -30
    print("TX gain chan1:", sdr.tx_hardwaregain_chan1) #Attenuation applied to TX path, -10
    print("TX enabled channels:", sdr.tx_enabled_channels) 
    print("RX enabled channels:", sdr.rx_enabled_channels)
    print("RX buffer size:", sdr.rx_buffer_size) #1024

    print("TX LO: %s" % (sdr.tx_lo)) #Carrier frequency of TX path
    print("RX LO: %s" % (sdr.rx_lo)) #Carrier frequency of RX path
    print("AGC Mode chan0:", sdr.gain_control_mode_chan0)
    print("AGC Mode chan1:", sdr.gain_control_mode_chan1)#Mode of receive path AGC. Options are: slow_attack, fast_attack, manual
    print("RX gain chan0:", sdr.rx_hardwaregain_chan0)#71
    print("RX gain chan1:", sdr.rx_hardwaregain_chan1)#71 Gain applied to RX path. Only applicable when gain_control_mode is set to ‘manual’
    print("rx_rf_bandwidth:", sdr.rx_rf_bandwidth) #4Mhz Bandwidth of front-end analog filter of RX path
    print("Sample rate:", sdr.sample_rate) #Sample rate RX and TX paths in samples per second
    print("DDS scales:", sdr.dds_scales)

def initPhaser(urladdress, my_sdr, Blackman=False):
    #my_phaser = adi.CN0566(uri=urladdress, sdr=my_sdr)
    my_phaser = CN0566(uri=urladdress, sdr=my_sdr)
    print("Phaser url: ", my_phaser.uri)
    print("Phaser already connected")

    # Initialize both ADAR1000s, set gains to max, and all phases to 0
    my_phaser.configure(device_mode="rx")
    my_phaser.load_gain_cal()
    my_phaser.load_phase_cal()
    for i in range(0, 8):
        my_phaser.set_chan_phase(i, 0)

    if Blackman == True:
        gain_list = [8, 34, 84, 127, 127, 84, 34, 8]  # Blackman taper
        for i in range(0, len(gain_list)):
            my_phaser.set_chan_gain(i, gain_list[i], apply_cal=True)
    else:
        # Set all antenna elements to half scale - a typical HB100 will have plenty of signal power.
        gain = 64 # 64 is about half scale
        for i in range(8):
            my_phaser.set_chan_gain(i, gain, apply_cal=False)
    
    return my_phaser

def configureADF4159(my_phaser, output_freq= 12.1e9, BW= 500e6, num_steps= 1000, ramp_time= 1e3):
    # Configure the ADF4159 Rampling PLL
    #final output is 12.1GHz-LO(2.1GHz)=10GHz, Ramp range is 10GHz~10.5Ghz(10GHz+500MHz)
    # output_freq = 12.1e9 
    # BW = 500e6
    # num_steps = 1000
    # ramp_time = 1e3  # us
    ramp_time_s = ramp_time / 1e6
    my_phaser.frequency = int(output_freq / 4)  # Output frequency divided by 4, there is /4 ahead of the ADF4159 RFIN
    my_phaser.freq_dev_range = int(
        BW / 4
    )  # frequency deviation range in Hz.  This is the total freq deviation of the complete freq ramp
    my_phaser.freq_dev_step = int(
        BW / num_steps
    )  # frequency deviation step in Hz.  This is fDEV, in Hz.  Can be positive or negative
    my_phaser.freq_dev_time = int(
        ramp_time
    )  # total time (in us) of the complete frequency ramp
    my_phaser.delay_word = 4095  # 12 bit delay word.  4095*PFD = 40.95 us.  For sawtooth ramps, this is also the length of the Ramp_complete signal
    my_phaser.delay_clk = "PFD"  # can be 'PFD' or 'PFD*CLK1'
    my_phaser.delay_start_en = 0  # delay start
    my_phaser.ramp_delay_en = 0  # delay between ramps.
    my_phaser.trig_delay_en = 0  # triangle delay
    my_phaser.ramp_mode = "continuous_triangular"  # ramp_mode can be:  "disabled", "continuous_sawtooth", "continuous_triangular", "single_sawtooth_burst", "single_ramp_burst"
    my_phaser.sing_ful_tri = (
        0  # full triangle enable/disable -- this is used with the single_ramp_burst mode
    )
    my_phaser.tx_trig_en = 0  # start a ramp with TXdata
    my_phaser.enable = 0  # 0 = PLL enable.  Write this last to update all the registers
    return my_phaser

def initAD9361(urladdress, fs, center_freq=2.2e9, rxbuffer=1024, Rx_CH=2, Tx_CH=2, rxbw=4000000, rxgain0=30, rxgain1=30, txgain0=-88, txgain1=-88):
    # Create radio
    sdr = adi.ad9361(uri=urladdress)
    sdr.rx_rf_bandwidth = int(rxbw) #4000000 #4MHz
    sdr.sample_rate = int(fs) 

    # Configure Rx
    #sdr.rx_enabled_channels = [0, 1]  # enable Rx1 (voltage0) and Rx2 (voltage1)
    # Configuration data channels
    if Rx_CH==2:
        sdr.rx_enabled_channels = [0,1] #enable two rx channel
        sdr.gain_control_mode_chan0 = "manual"  # manual or slow_attack
        sdr.gain_control_mode_chan1 = "manual"  # manual or slow_attack
        sdr.rx_hardwaregain_chan0 = int(rxgain0)  # must be between -3 and 70
        sdr.rx_hardwaregain_chan1 = int(rxgain1)  # must be between -3 and 70
    else:
        sdr.rx_enabled_channels = [0] #enables Rx0
        sdr.gain_control_mode_chan0 = "manual"  # manual or slow_attack
        sdr.rx_hardwaregain_chan0 = int(30)  # must be between -3 and 70
    sdr.rx_buffer_size = int(rxbuffer)
    sdr.rx_lo = int(center_freq)  # set this to output_freq - (the freq of the HB100)
    #num_samps = 1024*100#10000 # number of samples returned per call to rx()
    #sdr.rx_buffer_size = num_samps

    #from mycn0566 SDR_init, LKK: these will cause sdr parameters to reset
    # sdr._ctrl.debug_attrs[
    #     "adi,frequency-division-duplex-mode-enable"
    # ].value = "1"  # set to fdd mode
    # sdr._ctrl.debug_attrs[
    #     "adi,ensm-enable-txnrx-control-enable"
    # ].value = "0"  # Disable pin control so spi can move the states
    # sdr._ctrl.debug_attrs["initialize"].value = "1"
    # sdr._rxadc.set_kernel_buffers_count(
    #     1
    # )  # Default is 4 Rx buffers are stored, but we want to change and immediately measure the result, so buffers=1

    # Configure Tx
    if Tx_CH==2:
        sdr.tx_enabled_channels = [0, 1]
        sdr.tx_hardwaregain_chan0 = txgain0  # must be between 0 and -88
        sdr.tx_hardwaregain_chan1 = txgain1  # must be between 0 and -88
    else:
        sdr.tx_enabled_channels = [0] #enables Tx0
        sdr.tx_hardwaregain_chan0 = txgain0  # must be between 0 and -88
    sdr.tx_cyclic_buffer = True  # must set cyclic buffer to true for the tdd burst mode.  Otherwise Tx will turn on and off randomly
    sdr.tx_lo = int(center_freq)
    # Enable TDD logic in pluto (this is for synchronizing Rx Buffer to ADF4159 TX input)
    # gpio = adi.one_bit_adc_dac(sdr_ip)
    # gpio.gpio_phaser_enable = True

    return sdr
    
def createcomplexsinusoid(fs, signal_freq = 100000, N = 1024):
    # Create a complex sinusoid
    #fc = 3000000
    #N = 1024 #rx buffer size
    #fs = int(sdr.tx_sample_rate)
    ts = 1 / float(fs)
    fc = int(signal_freq / (fs / N)) * (fs / N) #100KHz
    t = np.arange(0, N * ts, ts)
    i = np.cos(2 * np.pi * t * fc) * 2 ** 14
    q = np.sin(2 * np.pi * t * fc) * 2 ** 14
    iq = i + 1j * q
    return iq

def readiio(sdr):
    phy = sdr.ctx.find_device("ad9361-phy")
    # Read product ID register
    pi = phy.reg_read(0x37)
    #print(f"ID: {hex(pi)}")
    r = 0x80000088
    status = phy.reg_read(r)
    if status & 0b0100:
        print("Overflow")

def setupalldevices(sdrurl, phaserurl, Rx_CHANNEL, Tx_CHANNEL, fs, center_freq, signal_freq, fft_size):
    sample_rate=fs
    # Configure the ADF4159 Rampling PLL
    #final output is 12.1GHz-LO(2.1GHz)=10GHz, Ramp range is 10GHz~10.5Ghz(10GHz+500MHz)
    output_freq = 12.1e9 
    BW = 500e6
    num_steps = 1000
    ramp_time = 1e3  # us
    ramp_time_s = ramp_time / 1e6
    rxbw=4000000 #4Mhz

    #sdr=initAD9361(ad9361urladdress, sample_rate, center_freq, fft_size, Rx_CH=2, Tx_CH=2)
    sdr=initAD9361(sdrurl, sample_rate, center_freq, rxbuffer=fft_size, \
                   Rx_CH=Rx_CHANNEL, Tx_CH=Tx_CHANNEL, rxbw=rxbw, rxgain0=30, rxgain1=30, txgain0=-88, txgain1=0)
    sleep(1)
    my_phaser=initPhaser(phaserurl, sdr)

    # Aim the beam at boresight (zero degrees)
    my_phaser.set_beam_phase_diff(0.0)

    my_phaser=configureADF4159(my_phaser, output_freq, BW, num_steps, ramp_time)

    # Read properties
    print("RX LO %s" % (sdr.rx_lo)) #2Ghz
    printSDRproperties(sdr)

    # Print config
    print(
        """
    CONFIG:
    Sample rate: {sample_rate}MHz
    Num samples: 2^{Nlog2}
    Bandwidth: {BW}MHz
    Ramp time: {ramp_time}ms
    Output frequency: {output_freq}MHz
    IF: {signal_freq}kHz
    """.format(
            sample_rate=sample_rate / 1e6,
            Nlog2=int(np.log2(fft_size)),
            BW=BW / 1e6,
            ramp_time=ramp_time / 1e3,
            output_freq=output_freq / 1e6,
            signal_freq=signal_freq / 1e3,
        )
    )
    return sdr, my_phaser, BW, num_steps, ramp_time_s

class RadarData:
    def __init__(self, datapath='./data/radardata5s-1101fast3move.npy', samplerate=0.6e6, rxbuffersize=1024*16):
        with open(datapath, 'rb') as f:
            self.alldata = np.load(f)
        print(len(self.alldata))
        self.samplerate = samplerate
        self.rxbuffersize=rxbuffersize
        self.totallen=len(self.alldata)
        self.Ntotalframe=int(self.totallen/rxbuffersize)-1
        self.signal_freq = 100e3 #100K
        self.BW = 500e6
        self.ramp_time = 1e3  # us
        self.ramp_time_s = self.ramp_time / 1e6
        self.num_steps = 1000
        
    def returnparameters(self):
        c = 3e8
        fs= int(self.samplerate)
        freq = np.linspace(-fs / 2, fs / 2, self.rxbuffersize)
        self.slope = self.BW / self.ramp_time_s
        print("Slope: %0.2fMHz/s" % (self.slope / 1e6))
        self.N_s = int(self.ramp_time_s * fs) #Number ADC sampling points in each chirp, 600
        self.N_c = int(self.rxbuffersize/self.N_s)-1 #number of chirps in fft_size
        dist = (freq - self.signal_freq) * c / (4 * self.slope)
        range_resolution = c / (2 * self.BW) #0.3
        range_x = (self.signal_freq) * c / (4 * self.slope) #15
        return c, self.BW, self.num_steps, self.ramp_time_s, self.slope, self.N_c, self.N_s, freq, dist, range_resolution, self.signal_freq, range_x


    def receive(self, index):
        self.currentindex = index
        if self.currentindex>=self.Ntotalframe:
            print("Finished one round data")
            self.currentindex=0
        start = timer()
        currentdata = self.alldata[self.currentindex*self.rxbuffersize:(self.currentindex+1)*self.rxbuffersize]
        rxt = timer()
        timedelta=rxt-start
        self.currentindex= self.currentindex+1
        return currentdata, len(currentdata), self.currentindex


class PhaserDevice:
    def __init__(self, phaserurl, sdr, vco_freq, BW=500e6, ramp_time=0.5e3, device_mode="rx", Blackman= True, tddmode=False):
        #my_phaser = adi.CN0566(uri=rpi_ip, sdr=my_sdr)
        my_phaser = CN0566(uri=phaserurl, sdr=sdr)
        print("Phaser url: ", my_phaser.uri)
        print("Phaser already connected")

        # Initialize both ADAR1000s, set gains to max, and all phases to 0
        my_phaser.configure(device_mode=device_mode)
        my_phaser.load_gain_cal()
        my_phaser.load_phase_cal()
        for i in range(0, 8):
            my_phaser.set_chan_phase(i, 0)

        if Blackman == True:
            gain_list = [8, 34, 84, 127, 127, 84, 34, 8]  # Blackman taper
            for i in range(0, len(gain_list)):
                my_phaser.set_chan_gain(i, gain_list[i], apply_cal=True)
        else:
            # Set all antenna elements to half scale - a typical HB100 will have plenty of signal power.
            gain = 64 # 64 is about half scale
            for i in range(8):
                my_phaser.set_chan_gain(i, gain, apply_cal=False)
    
        self.my_phaser = my_phaser
        self.setupPiGPIO() #new added
        self.setupADF4159(vco_freq=vco_freq, ramp_time=ramp_time, BW=BW, tddmode=tddmode)
    
    def setupADF4159(self, vco_freq=12.145e9, ramp_time=0.5e3, BW= 500e6, tddmode=False):
        # Configure the ADF4159 Rampling PLL
        my_phaser = self.my_phaser
        #BW = 500e6
        #num_steps = 500
        num_steps = int(ramp_time)    # in general it works best if there is 1 step per us
        #ramp_time = 0.5e3  # us
        #output_freq = 12.145e9
        #vco_freq = int(output_freq + signal_freq + center_freq) #12.1GHz
        my_phaser.frequency = int(vco_freq / 4)  # Output frequency divided by 4
        my_phaser.freq_dev_range = int(
            BW / 4
        )  # frequency deviation range in Hz.  This is the total freq deviation of the complete freq ramp
        my_phaser.freq_dev_step = int(
            (BW/4) / num_steps
        )  # frequency deviation step in Hz.  This is fDEV, in Hz.  Can be positive or negative
        my_phaser.freq_dev_time = int(
            ramp_time
        )  # total time (in us) of the complete frequency ramp
        print("requested freq dev time = ", ramp_time)
        ramp_time = my_phaser.freq_dev_time
        ramp_time_s = ramp_time / 1e6
        print("actual freq dev time = ", ramp_time)
        my_phaser.delay_word = 4095  # 12 bit delay word.  4095*PFD = 40.95 us.  For sawtooth ramps, this is also the length of the Ramp_complete signal
        my_phaser.delay_clk = "PFD"  # can be 'PFD' or 'PFD*CLK1'
        my_phaser.delay_start_en = 0  # delay start
        my_phaser.ramp_delay_en = 0  # delay between ramps.
        my_phaser.trig_delay_en = 0  # triangle delay
        if tddmode:
            my_phaser.ramp_mode = "single_sawtooth_burst"
            ##"continuous_triangular"  # ramp_mode can be:  "disabled", "continuous_sawtooth", "continuous_triangular", "single_sawtooth_burst", "single_ramp_burst"
            my_phaser.tx_trig_en = 1  # start a ramp with TXdata
        else:
            my_phaser.ramp_mode = "continuous_triangular"
            my_phaser.tx_trig_en = 0  # start a ramp with TXdata
        my_phaser.sing_ful_tri = (
            0  # full triangle enable/disable -- this is used with the single_ramp_burst mode
        )
        my_phaser.enable = 0  # 0 = PLL enable.  Write this last to update all the registers


    def setupPiGPIO(self):
        # Setup Raspberry Pi GPIO states
        try:
            self.my_phaser._gpios.gpio_tx_sw = 0  # 0 = TX_OUT_2, 1 = TX_OUT_1
            self.my_phaser._gpios.gpio_vctrl_1 = 1 # 1=Use onboard PLL/LO source  (0=disable PLL and VCO, and set switch to use external LO input)
            self.my_phaser._gpios.gpio_vctrl_2 = 1 # 1=Send LO to transmit circuitry  (0=disable Tx path, and send LO to LO_OUT)
        except:
            self.my_phaser.gpios.gpio_tx_sw = 0  # 0 = TX_OUT_2, 1 = TX_OUT_1
            self.my_phaser.gpios.gpio_vctrl_1 = 1 # 1=Use onboard PLL/LO source  (0=disable PLL and VCO, and set switch to use external LO input)
            self.my_phaser.gpios.gpio_vctrl_2 = 1 # 1=Send LO to transmit circuitry  (0=disable Tx path, and send LO to LO_OUT)

        

class RadarDevice:
    def __init__(self, sdrurl, phaserurl, sample_rate=0.6e6, center_freq=2.1e9, \
                 rxbuffersize = 1024*8, rx_gain=20, Rx_CHANNEL = 2, Tx_CHANNEL = 2,\
                signal_freq = 100e3, bandwidth = 4000000, output_freq = 10e9, tddmode=False):
        self.Rx_CHANNEL = Rx_CHANNEL
        self.Tx_CHANNEL = Tx_CHANNEL
        self.center_freq = center_freq #2.1e9 #fc=2.1G
        self.rxbuffersize=rxbuffersize #fft_size
        self.tddmode = tddmode
        self.mysdr = SDR(SDR_IP=sdrurl, SDR_FC=self.center_freq, \
                        SDR_SAMPLERATE=sample_rate, SDR_BANDWIDTH=1e6, \
                            Rx_CHANNEL=Rx_CHANNEL, Tx_CHANNEL=Tx_CHANNEL)
        self.mysdr.SDR_TX_stop()
        # must set cyclic buffer to true for the tdd burst mode.  Otherwise Tx will turn on and off randomly
        self.mysdr.SDR_TX_setup(cyclic_buffer=True, tx1_gain=-88, tx2_gain=0)
        self.mysdr.SDR_RX_setup(n_SAMPLES=rxbuffersize, controlmode='manual', rx1_gain=rx_gain, rx2_gain=rx_gain) ## set the RX buffer size to 3 times the number of samples
        #self.mysdr.SDR_gain_set(tx_gain=0, rx_gain=30)

        self.signal_freq = signal_freq #100e3 #100K
        self.bandwidth = bandwidth #4000000 #4MHz
        #output_freq = 10e9 #10GHz
        ramp_time = 0.5e3 # ramp time in us
        #num_steps = 500
        self.num_steps = int(ramp_time)    # in general it works best if there is 1 step per us
        vco_freq = int(output_freq + signal_freq + center_freq) #12.1GHz
        myphaser = PhaserDevice(phaserurl=phaserurl, sdr=self.mysdr.sdr, vco_freq=vco_freq, BW=bandwidth, ramp_time=ramp_time, tddmode=tddmode)
        
        #Read parameters from device
        self.ramp_time = myphaser.my_phaser.freq_dev_time
        self.ramp_time_s = self.ramp_time / 1e6
        self.sample_rate = int(self.mysdr.sdr.sample_rate) #0.6MHz
        self.fft_size = int(self.mysdr.sdr.rx_buffer_size) #8192
        
        # Print config
        c = 3e8
        wavelength = c / output_freq #0.03
        freq = np.linspace(-self.sample_rate / 2, self.sample_rate / 2, int(self.fft_size)) #(8192,)
        slope = bandwidth / self.ramp_time_s #1e12
        dist = (freq - signal_freq) * c / (2 * slope) #(8192,)
        plot_dist = False
        print(
            """
        CONFIG:
        Sample rate: {sample_rate}MHz
        Num samples: 2^{Nlog2}
        Bandwidth: {BW}MHz
        Ramp time: {ramp_time}ms
        Output frequency: {output_freq}MHz
        IF: {signal_freq}kHz
        """.format(
                sample_rate=sample_rate / 1e6, #0.6MHz
                #Nlog2=int(np.log2(fft_size)),
                Nlog2=int(np.log2(self.fft_size)), #Num samples: 2^13
                BW=bandwidth / 1e6, #500Mhz
                ramp_time=self.ramp_time / 1e3, #0.5ms
                output_freq=output_freq / 1e6, #10Ghz
                signal_freq=signal_freq / 1e3, #100KHz
            )
        )

        # self.sdr, self.phaser, self.BW, self.num_steps, self.ramp_time_s=setupalldevices(sdrurl, phaserurl, self.Rx_CHANNEL, self.Tx_CHANNEL, self.samplerate, \
        #                             self.center_freq, self.signal_freq, self.rxbuffersize)

        self.transmitsetup()
        self.transmit()
    
    def returnparameters(self):
        c = 3e8
        fs= int(self.sample_rate)
        freq = np.linspace(-fs / 2, fs / 2, self.rxbuffersize)
        self.slope = self.bandwidth / self.ramp_time_s
        print("Slope: %0.2fMHz/s" % (self.slope / 1e6))
        self.N_s = int(self.ramp_time_s * fs) #Number ADC sampling points in each chirp, 600
        self.N_c = int(self.rxbuffersize/self.N_s)-1 #number of chirps in fft_size
        dist = (freq - self.signal_freq) * c / (4 * self.slope)
        range_resolution = c / (2 * self.BW) #0.3
        range_x = (self.signal_freq) * c / (4 * self.slope) #15
        return c, self.bandwidth, self.num_steps, self.ramp_time_s, self.slope, self.N_c, self.N_s, freq, dist, range_resolution, self.signal_freq, range_x

    def transmitsetup(self, signaltype='sinusoid'):
        fs = int(self.sample_rate) #0.6MHz
        print("sample_rate:", fs)
        N = int(self.fft_size)#sdr.rx_buffer_size)
        if signaltype=='sinusoid':
            self.iq = createcomplexsinusoid(fs, self.signal_freq, N)
            iq_300k = createcomplexsinusoid(fs, self.signal_freq*3, N)
        #self.sdr._ctx.set_timeout(0)
        self.mysdr.sdr._ctx.set_timeout(30000)
        if self.tddmode:
            self.mysdr.sdr._rx_init_channels()
    
    def transmit(self):
        #self.sdr.tx([self.iq * 0.5, self.iq])  # only send data to the 2nd channel (that's all we need)
        self.mysdr.SDR_TX_send(SAMPLES=self.iq * 0.5, SAMPLES2=self.iq, leadingzeros=0, cyclic=True)
    
    def receive(self, index):
        self.currentindex = index
        start = timer()
        x = self.sdr.rx() #1024 size array of complex
        rxt = timer()
        timedelta=rxt-start
        if self.Rx_CHANNEL==2:
            data0=x[0]
            data1=x[1]
            data = data0 + data1
        else:
            data=x
        datalen=len(data.real)
        datarate=datalen*4/timedelta/1e6 #Mbps, complex data is 4bytes
        print("Data rate at ", datarate, "Mbps.") #7-8Mbps in 10240 points, 10Mbps in 102400points, single channel in 19-20Mbps
        self.currentindex = self.currentindex +1
        return data, datalen, self.currentindex

def create_folder_and_save_array(folder_path, array, filename='data.npy'):
    # Check if the folder exists, create it if not
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    # Save the NumPy array to a file (e.g., 'data.npy') in the folder
    np.save(os.path.join(folder_path, filename), array)

def radardata_collect(phaserurladdress, ad9361urladdress, Rx_CHANNEL, Tx_CHANNEL, signal_type, plot_flag, filename='radardata5s-0616a.npy'):
    # Configure properties
    #fs= 6000000 #6MHz
    fs = 0.6e6 #0.6M
    center_freq = 2.1e9 #2.1G
    signal_freq = 100e3 #100K
    num_slices = 200
    fft_size = 1024 * 16 #*10
    img_array = np.zeros((num_slices, fft_size))

    sdr, my_phaser, BW, num_steps, ramp_time_s = setupalldevices(ad9361urladdress, phaserurladdress, Rx_CHANNEL, Tx_CHANNEL, fs, center_freq, signal_freq, fft_size)


    fs = int(sdr.sample_rate) #0.6MHz
    print("sample_rate:", fs)
    N = int(sdr.rx_buffer_size)
    iq = createcomplexsinusoid(fs, signal_freq, N)
    iq_300k = createcomplexsinusoid(fs, signal_freq*3, N)

    # Send data
    sdr._ctx.set_timeout(0)
    sdr.tx([iq * 0.5, iq])  # only send data to the 2nd channel (that's all we need)

    c = 3e8
    default_rf_bw = BW #500e6
    N_frame = fft_size
    freq = np.linspace(-fs / 2, fs / 2, int(N_frame))
    slope = BW / ramp_time_s
    dist = (freq - signal_freq) * c / (4 * slope)

    xdata = freq
    plot_dist = False

    print("Slope: %0.2fMHz/s" % (slope / 1e6))
    range_resolution = c / (2 * default_rf_bw) #0.3
    range_x = (100e3) * c / (4 * slope) #15
    #0, range_x or frequency 100e3, 200e3

    # Collect data
    alldata0 = np.empty(0, dtype=np.complex_) #Default is numpy.float64.
    rxtime=[]
    processtime=[]
    Nperiod=int(5*fs/fft_size) #total time 10s *fs=total samples /fft_size = Number of frames
    print("Total period for 5s:", Nperiod) #73
    for r in range(Nperiod):
        start = timer()
        x = sdr.rx() #1024 size array of complex
        rxt = timer()
        timedelta=rxt-start
        rxtime.append(timedelta)
        if Rx_CHANNEL==2:
            data0=x[0]
            data1=x[1]
            data = data0 + data1
        else:
            data=x
        datarate=len(data.real)*4/timedelta/1e6 #Mbps, complex data is 4bytes
        print("Data rate at ", datarate, "Mbps.") #7-8Mbps in 10240 points, 10Mbps in 102400points, single channel in 19-20Mbps
        alldata0 = np.concatenate((alldata0, data))

        readiio(sdr)
        endtime = timer()
        processtime.append(endtime-start)
    
        # Stop transmitting
    sdr.tx_destroy_buffer() #Clears TX buffer
    sdr.rx_destroy_buffer() #Clears RX buffer
    create_folder_and_save_array(folder_path='./data/', array=alldata0, filename=filename)
    # with open('./data/radardata5s-1101fast4move.npy', 'wb') as f:
    #     np.save(f, alldata0)
    print(len(alldata0)) #1196032

def main():
    args = parser.parse_args()
    phaserurladdress = args.phaserurladdress #urladdress #"ip:pluto.local"
    ad9361urladdress = args.ad9361urladdress
    Rx_CHANNEL = args.rxch
    Tx_CHANNEL = args.txch
    signal_type = args.signal
    plot_flag = args.plot

    radardata_collect(phaserurladdress, ad9361urladdress, Rx_CHANNEL, Tx_CHANNEL, signal_type, plot_flag, filename='radardata5s-0616a.npy')
    
    
# piuri="ip:phaser.local:50901"
# localuri="ip:analog.local"
# antsdruri="ip:192.168.1.10"#connected via Ethernet with static IP
# plutodruri="ip:192.168.2.16"#connected via USB

import argparse
parser = argparse.ArgumentParser(description='MyRadar')
parser.add_argument('--ad9361urladdress', default="ip:192.168.1.67:50901", type=str,
                    help='urladdress of the device') #ip:pluto.local, ip:phaser.local:50901
parser.add_argument('--phaserurladdress', default="ip:192.168.1.67", type=str,
                    help='urladdress of the device, ip:phaser.local')
parser.add_argument('--rxch', default=2, type=int, 
                    help='number of rx channels')
parser.add_argument('--txch', default=2, type=int, 
                    help='number of rx channels')
parser.add_argument('--signal', default="dds", type=str,
                    help='signal type: sinusoid, dds')
parser.add_argument('--plot', default=False, type=bool,
                    help='plot figure')

if __name__ == '__main__':
    main()