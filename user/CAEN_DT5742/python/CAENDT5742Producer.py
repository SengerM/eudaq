#! /usr/bin/env python3
# load binary lib/pyeudaq.so
import sys
sys.path.insert(1, '/home/msenger/code/eudaq/lib') # Added this for testing, otherwise get error to import `pyeudaq`.
import pyeudaq
from pyeudaq import EUDAQ_INFO, EUDAQ_ERROR
from CAENpy.CAENDigitizer import CAEN_DT5742_Digitizer # https://github.com/SengerM/CAENpy
import pickle

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
		self._digitizer.set_record_length(1024)
		self._digitizer.set_acquisition_mode('sw_controlled')
		self._digitizer.set_ext_trigger_input_mode('disabled')
		self._digitizer.set_fast_trigger_mode(enabled=True)
		self._digitizer.set_fast_trigger_digitizing(enabled=True)
		self._digitizer.enable_channels(group_1=True, group_2=False)
		self._digitizer.set_fast_trigger_DC_offset(V=0)

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
			event = pyeudaq.Event("RawEvent", "sub_name")
			event.SetTriggerN(n_trigger)
			serialized_data = pickle.dumps(
				self._digitizer.get_waveforms(get_time=True, get_ADCu_instead_of_volts=True)
			)
			event.AddBlock(
				0, # `id`, whatever that means.
				serialized_data, # `data`, the data to append.
			)
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
