#! /usr/bin/env python3
# load binary lib/pyeudaq.so
import sys
from pathlib import Path
sys.path.insert(1, str((Path(__file__).parent.parent.parent.parent/'lib').resolve())) # Here is where `pyeudaq` lies.
import pyeudaq
from pyeudaq import EUDAQ_INFO, EUDAQ_ERROR
from CAENpy.CAENDigitizer import CAEN_DT5742_Digitizer # https://github.com/SengerM/CAENpy
import pickle
import ast
import numpy

DIGITIZER_RECORD_LENGTH = 1024

def parse_channels_mapping(channels_mapping_str:str):
	"""Parse the `channels_mapping` config parameter and returns the 
	expected dictionary. Also raises `ValueError` if anything is wrong."""
	try:
		channels_mapping = ast.literal_eval(channels_mapping_str)
	except Exception as e:
		raise ValueError(f'Cannot parse `channels_mapping` into a Python object, probably there is a syntax error in your config file. The error raised by the method in charge of the parsing is: {repr(e)}')
	if not isinstance(channels_mapping, dict):
		raise ValueError(f'`channels_mapping` should be a dictionary, received instead an object of type {type(channels_mapping)}')
	for k,i in channels_mapping.items():
		if not isinstance(k, str):
			raise ValueError(f'The keys of `channels_mapping` must be strings containing the names of each plane, but received `{repr(k)}` of type {type(k)}')
		if not isinstance(i, list) or any([not isinstance(_,list) for _ in i]) or any([len(i[0])!=len(_) for _ in i]):
			raise ValueError(f'Each item of `channels_mapping` must be a two dimensional array specified as a list of lists with dimensions X×Y being X the number of pixels in x and Y the number of pixels in Y')
		if any([not isinstance(_,str) for __ in i for _ in __]):
			raise ValueError(f'The elements inside the lists of `channels_mapping` must be strings with the channels names from the CAEN, e.g. `"CH1"`.')
	return channels_mapping

def exception_handler(method):
	def inner(*args, **kwargs):
		try:
			return method(*args, **kwargs)
		except Exception as e:
			EUDAQ_ERROR(str(e))
			raise e
	return inner

class CAENDT5742Producer(pyeudaq.Producer):
	def __init__(self, name, runctrl):
		pyeudaq.Producer.__init__(self, name, runctrl)
		self.is_running = 0
		EUDAQ_INFO('CAENDT5742Producer: New instance')

	@exception_handler
	def DoInitialise(self):
		LinkNum = self.GetInitItem('LinkNum')
		if LinkNum == '': # This happens when the parameter is not specified.
			raise RuntimeError(f'The init parameter `LinkNum` (type int) must be provided in the init file.')
		try:
			LinkNum = int(LinkNum)
		except Exception as e:
			raise ValueError(f'The parameter `LinkNum` must be an integer, received {repr(LinkNum)}. ')
		self._digitizer = CAEN_DT5742_Digitizer(LinkNum=LinkNum)

	@exception_handler
	def DoConfigure(self):
		CONFIGURE_PARAMS = {
			'sampling_frequency_MHz': dict(
				set_method = 'set_sampling_frequency',
				default = 5000,
				type = int,
			),
			'max_num_events_BLT': dict(
				set_method = 'set_max_num_events_BLT',
				default = 1,
				type = int,
			),
			'fast_trigger_threshold_ADCu': dict(
				set_method = 'set_fast_trigger_threshold',
				type = int,
			),
			'post_trigger_size': dict(
				set_method = 'set_post_trigger_size',
				default = 1,
				type = int,
			),
			'trigger_polarity': dict(
				type = str,
			),
		}
		
		self._digitizer.reset() # Always better to start in a known state.
		
		channels_mapping_str = self.GetConfigItem('channels_mapping')
		self.channels_mapping = parse_channels_mapping(channels_mapping_str)
		self.channels_names_list = sorted([self.channels_mapping[ch][i][j] for ch in self.channels_mapping for i in range(len(self.channels_mapping[ch])) for j in range(len(self.channels_mapping[ch][i]))]) # This is the order in which the data will be stored, i.e. which channel first, which second, etc.
		
		# Parse parameters and raise errors if necessary:
		for param_name in CONFIGURE_PARAMS:
			received_param_value = self.GetConfigItem(param_name)
			param_value_to_be_configured = received_param_value if received_param_value != '' else CONFIGURE_PARAMS[param_name].get('default')
			if param_value_to_be_configured is None: # This means it is mandatory and was not specified, i.e. there is no default value.
				raise RuntimeError(f'Configuration parameter {repr(param_name)} is mandatory and was not specified in the configuration file. ')
			try: # Convert to the correct data type...
				param_value_to_be_configured = CONFIGURE_PARAMS[param_name]['type'](param_value_to_be_configured)
			except Exception as e:
				raise ValueError(f'The parameter `{param_name}` must be of type {CONFIGURE_PARAMS[param_name]["type"]}, received {repr(received_param_value)}. ')
			CONFIGURE_PARAMS[param_name]['value'] = param_value_to_be_configured
		
		# Automatically configure those parameters which are easy to configure:
		for param_name in CONFIGURE_PARAMS:
			if CONFIGURE_PARAMS[param_name].get('set_method') is not None: # Then we can automatically set it here, otherwise do it manually below.
				getattr(self._digitizer, CONFIGURE_PARAMS[param_name]['set_method'])(CONFIGURE_PARAMS[param_name]['value'])
		
		# Manual configuration of parameters:
		for ch in [0,1]:
			self._digitizer.set_trigger_polarity(channel=ch, edge=CONFIGURE_PARAMS['trigger_polarity']['value'])
		
		# Some non-configurable settings:
		self._digitizer.set_record_length(DIGITIZER_RECORD_LENGTH)
		self._digitizer.set_acquisition_mode('sw_controlled')
		self._digitizer.set_ext_trigger_input_mode('disabled')
		self._digitizer.set_fast_trigger_mode(enabled=True)
		self._digitizer.set_fast_trigger_digitizing(enabled=True)
		self._digitizer.enable_channels(group_1=any([f'CH{n}' in self.channels_names_list for n in [0,1,2,3,4,5,6,7]]), group_2=any([f'CH{n}' in self.channels_names_list for n in [8,9,10,11,12,13,14,15]]))
		self._digitizer.set_fast_trigger_DC_offset(V=0)
		
		# Enable busy signal on GPO:
		self._digitizer.write_register(
			address = 0x811C, # Front Panel I/O Control, see '742 Raw Waveform Registers Description' in https://www.caen.it/products/dt5742/ → Downloads.
			data = (0
				| 0b1<<0 # TTL standard.
				| 0b01<<16 #  Motherboard Probes: TRG‐OUT/GPO is used to propagate signals of the motherboards according to bits[19:18].
				| 0b11<<18 # BUSY/UNLOCK: this is the board BUSY in case of ROC FPGA firmware rel. 4.5 or lower. This probe can be selected according to bit[20].
				| 0b0<<20 # If bits[19:18] = 11, then bit[20] options are: 0 = Board BUSY.
			)
		)

	@exception_handler
	def DoStartRun(self):
		self._digitizer.start_acquisition()
		self.is_running = 1
		
	@exception_handler
	def DoStopRun(self):
		self._digitizer.stop_acquisition()
		self.is_running = 0

	@exception_handler
	def DoReset(self):
		if hasattr(self, '_digitizer'):
			self._digitizer.close()
			delattr(self, '_digitizer')
		self.is_running = 0

	@exception_handler
	def RunLoop(self):
		n_trigger = 0;
		while(self.is_running):
			if self._digitizer.get_acquisition_status()['at least one event available for readout'] == True:
				waveforms = self._digitizer.get_waveforms(get_time=False, get_ADCu_instead_of_volts=True)
				serialized_data = numpy.concatenate(
					[waveforms[0][ch]['Amplitude (ADCu)'] for ch in self.channels_names_list],
					dtype = numpy.float32, # Hardcode data type to be sure it is always the same. (Though you would expect `int` here, CAENDigitizer library returns floats...)
				)
				serialized_data = serialized_data.tobytes()
				
				event = pyeudaq.Event("RawEvent", "CAEN_DT5748") # Not sure what these strings exactly are...
				event.SetTriggerN(n_trigger)
				event.AddBlock(
					n_trigger, # `id`, whatever that means.
					serialized_data, # `data`, the data to append.
				)
				
				if n_trigger == 0: # Add "header information".
					event.SetBORE() # beginning-of-run-event (BORE). http://eudaq.github.io/manual/EUDAQUserManual_v2_0_1.pdf#glo%3ABORE
					event.SetTag('channels_mapping_str', repr(self.channels_mapping)) # Literally whatever the `channels_mapping` parameter in the config file was, e.g. `{'DUT_1': [['CH0','CH1'],['CH2','CH3']], 'DUT_2': [['CH4','CH5'],['CH6','CH7']]}`.
					event.SetTag('channels_names_list', repr(self.channels_names_list)) # A list with the channels that were acquired and in the order they are stored in the raw data, e.g. `['CH0','CH1','CH2',...]`
					event.SetTag('number_of_DUTs', repr(len(self.channels_mapping))) # Number of DUTs that were specified in `channels_mapping` in the config file.
					event.SetTag('sampling_frequency_MHz', repr(self._digitizer.get_sampling_frequency())) # Integer number.
					event.SetTag('n_samples_per_waveform', repr(DIGITIZER_RECORD_LENGTH)) # Number of samples per waveform to decode the raw data.
					n_dut = 0
					for dut_name, dut_channels in self.channels_mapping.items():
						dut_label = f'DUT_{n_dut}' # DUT_0, DUT_1, ...
						event.SetTag(f'{dut_label}_name', repr(dut_name)) # String with the name of the DUT, defined by the user in the config file as the key of the `channels_mapping` dictionary.
						event.SetTag(f'{dut_label}_channels_matrix', repr(dut_channels)) # List with channels names, e.g. `"[['CH0','CH1'],['CH2','CH3']]"`.
						event.SetTag(f'{dut_label}_channels_arrangement', repr([f'{item}: {i},{j}' for i,row in enumerate(dut_channels) for j,item in enumerate(row)])) # End up with something of the form `"['CH0: 0,0', 'CH1: 0,1', 'CH2: 1,0', 'CH3: 1,1']"`
						event.SetTag(f'{dut_label}_n_channels', repr(sum([len(_) for _ in dut_channels]))) # Number of channels (i.e. number of waveforms) belonging to this DUT.
						n_dut += 1
				self.SendEvent(event)
				n_trigger += 1

if __name__ == "__main__":
	import time
	
	myproducer = CAENDT5742Producer("CAEN_digitizer", "tcp://localhost:44000")
	print ("Connecting to runcontrol in localhost:44000...")
	myproducer.Connect()
	time.sleep(2)
	print('Ready!')
	while(myproducer.IsConnected()):
		time.sleep(1)
