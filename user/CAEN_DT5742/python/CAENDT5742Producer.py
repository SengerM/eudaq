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
		self._digitizer = CAEN_DT5742_Digitizer(0) # Should I do this here?
		EUDAQ_INFO(f'CAENDT5742Producer: DoInitialise, connected with {self._digitizer.idn}')

	@exception_handler
	def DoConfigure(self):
		EUDAQ_INFO('CAENDT5742Producer: DoConfigure')
		self._digitizer.reset()
		self._digitizer.set_sampling_frequency(MHz=5000)
		self._digitizer.set_record_length(1024)
		self._digitizer.set_max_num_events_BLT(1) # Maximum number of events per block transfer.
		self._digitizer.set_acquisition_mode('sw_controlled')
		self._digitizer.set_ext_trigger_input_mode('disabled')
		self._digitizer.set_fast_trigger_mode(enabled=True)
		self._digitizer.set_fast_trigger_digitizing(enabled=True)
		self._digitizer.enable_channels(group_1=True, group_2=False)
		self._digitizer.set_fast_trigger_DC_offset(V=0)
		self._digitizer.set_post_trigger_size(1)
		for ch in [0,1]:
			self._digitizer.set_trigger_polarity(channel=ch, edge='rising')
		self._digitizer.set_fast_trigger_threshold(26340)

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
	print ("connecting to runcontrol in localhost:44000", )
	myproducer.Connect()
	time.sleep(2)
	while(myproducer.IsConnected()):
		time.sleep(1)
