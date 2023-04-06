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
		LinkNum = int(self.GetInitItem('LinkNum'))
		if not hasattr(self, '_digitizer'):
			self._digitizer = CAEN_DT5742_Digitizer(LinkNum=LinkNum)
		EUDAQ_INFO(f'CAENDT5742Producer: DoInitialise, connected with {self._digitizer.idn}')

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
		}
		
		EUDAQ_INFO('CAENDT5742Producer: DoConfigure')
		self._digitizer.reset()
		
		for param_name in CONFIGURE_PARAMS:
			_ = self.GetConfigItem(param_name)
			CONFIGURE_PARAMS[param_name]['value'] = CONFIGURE_PARAMS[param_name]['type'](_) if _ != '' else CONFIGURE_PARAMS[param_name].get('default')
			param_value = CONFIGURE_PARAMS[param_name]['value']
			if param_value is None: # This means it is mandatory and was not specified, i.e. there is no default value.
				raise RuntimeError(f'Configuration parameter {repr(param_name)} is mandatory and was not specified in the configuration file. ')
			getattr(self._digitizer, CONFIGURE_PARAMS[param_name]['set_method'])(param_value)
			EUDAQ_INFO(f'CAENDT5742Producer: {repr(param_name)} was configured.')
		
		self._digitizer.set_record_length(1024)
		self._digitizer.set_acquisition_mode('sw_controlled')
		self._digitizer.set_ext_trigger_input_mode('disabled')
		self._digitizer.set_fast_trigger_mode(enabled=True)
		self._digitizer.set_fast_trigger_digitizing(enabled=True)
		self._digitizer.enable_channels(group_1=True, group_2=False)
		self._digitizer.set_fast_trigger_DC_offset(V=0)
		for ch in [0,1]:
			self._digitizer.set_trigger_polarity(channel=ch, edge='rising')

	@exception_handler
	def DoStartRun(self):
		EUDAQ_INFO('CAENDT5742Producer: DoStartRun')
		self._digitizer.start_acquisition()
		self.is_running = 1
		
	@exception_handler
	def DoStopRun(self):
		EUDAQ_INFO('CAENDT5742Producer: DoStopRun')
		self._digitizer.stop_acquisition()
		self.is_running = 0

	@exception_handler
	def DoReset(self):
		EUDAQ_INFO('CAENDT5742Producer: DoReset')
		if hasattr(self, '_digitizer'):
			self._digitizer.reset()
		self.is_running = 0

	@exception_handler
	def RunLoop(self):
		EUDAQ_INFO("CAENDT5742Producer: Start of RunLoop")
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
		EUDAQ_INFO("CAENDT5742Producer: End of RunLoop")

if __name__ == "__main__":
	import time
	
	myproducer = CAENDT5742Producer("CAEN_digitizer", "tcp://localhost:44000")
	print ("Connecting to runcontrol in localhost:44000...")
	myproducer.Connect()
	time.sleep(2)
	print('Ready!')
	while(myproducer.IsConnected()):
		time.sleep(1)
