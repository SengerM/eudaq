#include "eudaq/StdEventConverter.hh"
#include "eudaq/RawEvent.hh"
//~ #include <Python.h>

class CAEN_DT5748RawEvent2StdEventConverter: public eudaq::StdEventConverter {
	public:
		bool Converting(eudaq::EventSPC d1, eudaq::StdEventSP d2, eudaq::ConfigSPC conf) const override;
		static const uint32_t m_id_factory = eudaq::cstr2hash("CAEN_DT5748");
	private:
		void Initialize(eudaq::EventSPC bore, eudaq::ConfigurationSPC conf) const;
		mutable size_t n_samples_per_waveform;
		mutable size_t sampling_frequency_MHz;
		mutable size_t number_of_DUTs;
		mutable std::vector<std::string> channels_names_list;
		mutable std::vector<std::string> DUTs_names;
		mutable std::vector<std::vector<std::vector<size_t>>> waveform_position; // waveform_position[n_DUT][nxpixel][nypixel] = position where this waveform begins in the raw data.
};

namespace {
	auto dummy0 = eudaq::Factory<eudaq::StdEventConverter>::Register<CAEN_DT5748RawEvent2StdEventConverter>(CAEN_DT5748RawEvent2StdEventConverter::m_id_factory);
}

void CAEN_DT5748RawEvent2StdEventConverter::Initialize(eudaq::EventSPC bore, eudaq::ConfigurationSPC conf) const {
	std::string s;
	
	n_samples_per_waveform = std::stoi(bore->GetTag("n_samples_per_waveform"));
	sampling_frequency_MHz = std::stoi(bore->GetTag("sampling_frequency_MHz"));
	number_of_DUTs = std::stoi(bore->GetTag("number_of_DUTs"));
	
	// Parse list with the names of the channels in the order they will appear in the raw data:
	s = bore->GetTag("channels_names_list");
	for (char c : {'[', ']', '\'', '\"'}) {
		s.erase(remove(s.begin(), s.end(), c), s.end());
	}
	std::string delimiter = ", ";
	size_t pos = 0;
	while ((pos = s.find(delimiter)) != std::string::npos) {
		std::string token = s.substr(0, pos);
		channels_names_list.push_back(token);
		s.erase(0, pos + delimiter.length());
	}
	channels_names_list.push_back(s);
	
	// For each DUT, build a matrix where the elements are integer numbers specifying the position where the respective waveform begins in the raw data:
	for (size_t n_DUT=0; n_DUT<number_of_DUTs; n_DUT++) {
		s = bore->GetTag(std::to_string(n_DUT)+"_channels"); // Gets something like e.g. `"[['CH0','CH1'],['CH2','CH3']]"` and want to recover the "vector of vectors of strings" structure.
		for (std::string c : {"[[", "]]", "'", "\""})
			s.erase(std::remove(s.begin(), s.end(), c[0]), s.end());
		// Split the string into a vector of strings:
		std::vector<std::string> parts;
		std::string delimiter = "],[";
		size_t pos = 0;
		std::string token;
		while ((pos = s.find(delimiter)) != std::string::npos) {
			token = s.substr(0, pos);
			parts.push_back(token);
			s.erase(0, pos + delimiter.length());
		}
		parts.push_back(s);
		// Split each part into a vector of strings:
		std::vector<std::vector<std::string>> matrix_with_channels_arrangement_for_this_DUT;
		delimiter = ",";
		for (std::string part : parts) {
			std::vector<std::string> row;
			pos = 0;
			while ((pos = part.find(delimiter)) != std::string::npos) {
				token = part.substr(0, pos);
				row.push_back(token);
				part.erase(0, pos + delimiter.length());
			}
			row.push_back(part);
			matrix_with_channels_arrangement_for_this_DUT.push_back(row);
		}
		
		// Now find where each of the channels waveforms begins in the raw data and arrange that into a matrix:
		std::vector<std::vector<size_t>> matrix2;
		for (size_t nx=0; nx<matrix_with_channels_arrangement_for_this_DUT.size(); nx++) {
			std::vector<size_t> row;
			for (size_t ny=0; ny<matrix_with_channels_arrangement_for_this_DUT[nx].size(); ny++) {
				auto iterator = std::find(channels_names_list.begin(), channels_names_list.end(), std::string("CH1"));//matrix_with_channels_arrangement_for_this_DUT[nx][ny]);
				if (iterator != channels_names_list.end()) {
					row.push_back((iterator - channels_names_list.begin())*n_samples_per_waveform);
				} else { // This should never happen.
					EUDAQ_THROW("Channel " + matrix_with_channels_arrangement_for_this_DUT[nx][ny] + " not present in the list of channels that were recorded.");
				}
			}
			matrix2.push_back(row);
		}
		waveform_position.push_back(matrix2); // Finally... In Python this is no more than 5 lines of code.
		DUTs_names.push_back(bore->GetTag(std::to_string(n_DUT)+"_name"));
	}
}

bool CAEN_DT5748RawEvent2StdEventConverter::Converting(eudaq::EventSPC d1, eudaq::StdEventSP d2, eudaq::ConfigSPC conf) const {
	if (d1->IsBORE()) { // Beginning Of Run Event, this is the header event.
		EUDAQ_INFO("Starting initialization...");
		Initialize(d1, conf);
	}
	
	std::cout << n_samples_per_waveform << std::endl;
	std::cout << sampling_frequency_MHz << std::endl;
	std::cout << number_of_DUTs << std::endl;
	for (std::string _: channels_names_list)
		std::cout << _ << std::endl;
	
	EUDAQ_THROW("Not implemented!");
	//~ PyObject *signals_package = import("signals") // This is what I use normally to parse the waveforms, https://github.com/SengerM/signals
	//~ auto ev = std::dynamic_pointer_cast<const eudaq::RawEvent>(d1);
	//~ size_t nblocks= ev->NumBlocks();
	//~ auto block_n_list = ev->GetBlockNumList();
	//~ for(auto &block_n: block_n_list){
		//~ auto block = ev->GetBlock(block_n);
		//~ uint8_t n_planes = block[wherever_the_number_of_planes_is];
		//~ for (uint8_t n_plane = 0; n_plane < n_planes; n_plane++) { // One plane per DUT connected to the digitizer.
			//~ eudaq::StandardPlane plane(block_n, "LGAD_CAEN", "LGAD_CAEN");
			//~ for (size_t n_xpixel = 0; n_xpixel < block[wherever_number_of_xpixels_is]; n_xpixel++) {
				//~ for (size_t n_ypixel = 0; n_ypixel < block[wherever_number_of_ypixels_is]; n_ypixel++) {
					//~ PyObject *signal = signals_package->signal_from_samples(block[wherever_nplane_nx_ny_waveform_begins:wherever_nplane_nx_ny_waveform_ends])
					//~ if (pixel_was_hit(signal)) // E.g. charge > some_threshold or whatever criterion using the waveform.
						//~ plane.PushPixel(n_xpixel, n_ypixel, signal.charge(), signal.hit_time());
				//~ }
			//~ }
			//~ plane.SetSizeZS(m_sizeX, m_sizeY, 0, 1, eudaq::StandardPlane::FLAG_DIFFCOORDS | eudaq::StandardPlane::FLAG_ACCUMULATE);
			//~ d2->AddPlane(plane);
		//~ }
	//~ }
	//~ return true;
}
