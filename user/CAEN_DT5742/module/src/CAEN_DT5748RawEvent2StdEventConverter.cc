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
		DUTs_names.push_back(bore->GetTag("DUT_"+std::to_string(n_DUT)+"_name"));
		s = bore->GetTag("DUT_"+std::to_string(n_DUT)+"_channels_matrix"); // Gets something like e.g. `"[['CH4', 'CH5'], ['CH6', 'CH7']]"`.
		if (s.empty())
			EUDAQ_THROW("Cannot get information about the channels to which the DUT named \""+DUTs_names[n_DUT]+"\" was connected.");
		std::vector<std::string> delims = {"[[", "]]", "'", "\"", " "};
		for (std::string delim : delims) {
			size_t pos = s.find(delim);
			while (pos != std::string::npos) {
				s.erase(pos, delim.length());
				pos = s.find(delim, pos);
			}
		}
		// Here `s` looks like e.g. `"CH4,CH5],[CH6,CH7"`.
		std::vector<std::string> split_s;
		size_t start_pos = 0;
		size_t end_pos = s.find("],[");
		while (end_pos != std::string::npos) {
			split_s.push_back(s.substr(start_pos, end_pos - start_pos));
			start_pos = end_pos + 3;
			end_pos = s.find("],[", start_pos);
		}
		split_s.push_back(s.substr(start_pos));
		// Here `split_s` looks like e.g. `["CH4,CH5"],["CH6,CH7"]` (Python).
		std::vector<std::vector<std::string>> matrix_with_channels_arrangement_for_this_DUT;
		for (std::string elem : split_s) {
			std::vector<std::string> sub_result;
			size_t sub_start_pos = 0;
			size_t sub_end_pos = elem.find(",");
			while (sub_end_pos != std::string::npos) {
				sub_result.push_back(elem.substr(sub_start_pos, sub_end_pos - sub_start_pos));
				sub_start_pos = sub_end_pos + 1;
				sub_end_pos = elem.find(",", sub_start_pos);
			}
			sub_result.push_back(elem.substr(sub_start_pos));
			matrix_with_channels_arrangement_for_this_DUT.push_back(sub_result);
		}
		// Here `matrix_with_channels_arrangement_for_this_DUT` should be `[['CH4', 'CH5'], ['CH6', 'CH7']]`.
		// Now find where each of the channels waveforms begins in the raw data and arrange that into a matrix:
		std::vector<std::vector<size_t>> matrix2;
		for (size_t nx=0; nx<matrix_with_channels_arrangement_for_this_DUT.size(); nx++) {
			std::vector<size_t> row;
			for (size_t ny=0; ny<matrix_with_channels_arrangement_for_this_DUT[nx].size(); ny++) {
				auto iterator = std::find(channels_names_list.begin(), channels_names_list.end(), matrix_with_channels_arrangement_for_this_DUT[nx][ny]);
				if (iterator != channels_names_list.end()) {
					row.push_back((iterator - channels_names_list.begin())*n_samples_per_waveform);
				} else { // This should never happen.
					EUDAQ_THROW("Channel " + matrix_with_channels_arrangement_for_this_DUT[nx][ny] + " not present in the list of channels that were recorded.");
				}
			}
			matrix2.push_back(row);
		}
		waveform_position.push_back(matrix2); // Finally... In Python this is no more than 5 lines of code.
	}
}

bool CAEN_DT5748RawEvent2StdEventConverter::Converting(eudaq::EventSPC d1, eudaq::StdEventSP d2, eudaq::ConfigSPC conf) const {
	auto event = std::dynamic_pointer_cast<const eudaq::RawEvent>(d1);
	if (event == nullptr) {
		EUDAQ_ERROR("Received null event.");
		return false;
	}
	
	if (event->IsBORE()) { // Beginning Of Run Event, this is the header event.
		EUDAQ_INFO("Starting initialization...");
		Initialize(event, conf);
	}
	
	std::cout << "n_samples_per_waveform: " << n_samples_per_waveform << std::endl;
	std::cout << "sampling_frequency_MHz: " << sampling_frequency_MHz << std::endl;
	std::cout << "number_of_DUTs: " << number_of_DUTs << std::endl;
	
	std::cout << "channels_names_list:" << std::endl;
	for (std::string _: channels_names_list)
		std::cout << _ << std::endl;
	
	std::cout << "DUTs_names:" << std::endl;
	for (std::string _: DUTs_names)
		std::cout << _ << std::endl;
	
	std::cout << "waveform_position:" << std::endl;
	for (size_t n_DUT=0; n_DUT<waveform_position.size(); n_DUT++) {
		for (size_t nx=0; nx<waveform_position[n_DUT].size(); nx++) {
			for (size_t ny=0; ny<waveform_position[n_DUT][nx].size(); ny++)
				std::cout << DUTs_names[n_DUT] << ", " << nx << ", " << ny << ", " << waveform_position[n_DUT][nx][ny] << std::endl;
		}
	}
	
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
