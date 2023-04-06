import os
import numpy as np
import math
import time
import SimpleITK as sitk

from help_function.niiCook import niiCook
from help_function import help_function as hlp

from kwave_function.kwave_input_file import KWaveInputFile
from kwave_function.kwave_output_file import KWaveOutputFile, DomainSamplingType, SensorSamplingType
from kwave_function.kwave_bin_driver import KWaveBinaryDriver

from scipy.optimize import differential_evolution

l2n = lambda l: np.array(l)
n2l = lambda n: list(n)

start = time.time()
current_path = os.path.dirname(__file__)

class makeSimulation():

    def __init__(self, path=False):

        print("Check init")
        ####################################################################
        # Material properties
        self.c_water = 1482  # [m/s]
        self.d_water = 1000  # [kg/m^3]
        self.a_water = 0.0253  # [Np/MHz/m]

        self.c_bone = 3100  # [m/s]    # 2800 or 3100 m/s
        self.d_bone = 2200  # [kg/m^3]
        self.a_bone_min = 21.5  # [Np/MHz/m]
        self.a_bone_max = 208.9  # [Np/MHz/m]

        self.alpha_power = 2.0

        ####################################################################
        # Source properties
        self.amplitude = 1  #  source pressure [Pa]
        self.source_freq = 25e4  # frequency [Hz]
        self.ROC = 99  # [mm]     # transducer setting
        self.width = 95  # [mm]
        self.focal_length = 85

        ####################################################################
        # Bounary condition
        self.boundary = 0

        ####################################################################
        # Time step
        self.CFL = 0.1
        self.end_time = 100e-6
        self.points_per_wavelength = np.pi*2 # number of grid points per wavelength at f0

        ####################################################################
        # Recording
        self.recording = False

        ####################################################################
        # Back propagation
        self.PHASE = []
        self.AMP = []
        self.back_source = []
        self.optimizer_check = 0

        ####################################################################
        # Path
        if path == False:
            self.path = current_path
        else:
            self.path = path

            try:
                os.mkdir(self.path)
            except:
                a=1

    def preprocessing(self, itk_image, target_pose):

        target_pose = np.multiply(target_pose, (-1, -1, 1)).astype(float)

        ####################################################################
        # Source properties
        dx = self.c_water / (self.points_per_wavelength * self.source_freq)  # [m]
        dy = dx
        dz = dx

        ####################################################################
        # Grid_size contains the PML (default 20)
        grid_res = (dx, dy, dz)

        ####################################################################
        # Skull process

        simul_domain = niiCook()
        simul_domain.readSavedFile(itk_image)
        skullCrop_itk, skullCrop_arr = simul_domain.makeSimulationDomain2(grid_res, self.focal_length, target_pose)


        print("Perform skull processing")
        print("Simulation domain: ", skullCrop_arr.shape)
        print("Simulation dx: ", dx)

        self.domainCook = niiCook()
        self.domainCook.readITK(skullCrop_itk)
        self.domainCook.saveITK(self.path+"\\skullCrop_itk.nii")

        self.dx = dx
        self.grid_res = grid_res
        self.target_pose = target_pose
        self.skullCrop_arr = skullCrop_arr
        self.rawCrop_arr = skullCrop_arr.copy()
        self.skullCrop_itk = skullCrop_itk
        self.domain_shape = skullCrop_arr.shape
        self.target_idx = np.array(skullCrop_itk.TransformPhysicalPointToIndex(target_pose)).astype(int)
        self.p0 = np.zeros(self.skullCrop_arr.shape)

    def free_water_run_simulation(self):

        # random vector for vertical direction
        target_pose = [0,0,10]
        ####################################################################
        # Source properties
        dx = self.c_water / (self.points_per_wavelength * self.source_freq)  # [m]
        dy = dx
        dz = dx

        ####################################################################
        # Grid_size contains the PML (default 20)
        grid_res = (dx, dy, dz)
        simul_spacing = l2n(grid_res) * 1000

        ####################################################################
        # Make reference image
        Nx = np.ceil(self.width/simul_spacing[0]) + 10
        Ny = Nx
        Nz = np.ceil((self.focal_length*1.7)/simul_spacing[2])+20

        domain = l2n([Nx, Ny, Nz])
        domain = domain - domain % 10

        x_end = -simul_spacing[0] * domain[0] / 2
        y_end = -simul_spacing[1] * domain[1] / 2
        z_end = -simul_spacing[2] * 20

        grid_origin = (x_end, y_end, z_end)

        reference_image = sitk.Image(int(domain[0]), int(domain[1]), int(domain[2]), sitk.sitkFloat32)
        reference_image.SetSpacing(simul_spacing)
        reference_image.SetOrigin(grid_origin)
        reference_image[:, :, :] = 0

        skullCrop_itk = reference_image
        skullCrop_arr = sitk.GetArrayFromImage(skullCrop_itk)

        ####################################################################
        # Save
        self.domainCook = niiCook()
        self.domainCook.readITK(skullCrop_itk)
        self.domainCook.saveITK(self.path+"\\skullCrop_rotate_itk.nii")

        self.dx = dx
        self.grid_res = grid_res
        self.target_pose = target_pose
        self.skullCrop_arr = skullCrop_arr
        self.rawCrop_arr = skullCrop_arr.copy()
        self.skullCrop_itk = skullCrop_itk
        self.domain_shape = skullCrop_arr.shape
        self.target_idx = np.array(skullCrop_itk.TransformPhysicalPointToIndex(target_pose)).astype(int)
        self.p0 = np.zeros(self.skullCrop_arr.shape)

        ####################################################################
        # Run simulation from free water // Transducer position is located at [0,0,0]
        self.make_transducer([0,0,0])
        self.run_simulation()

    def read_preprocessing(self, itk_image):

        domainCook = niiCook()
        domainCook.readSavedFile(itk_image)

        dx = domainCook.spacing[0]/1000
        dy = dx
        dz = dx

        grid_res = (dx, dy, dz)

        self.dx = dx
        self.grid_res = grid_res
        self.target_idx = l2n(domainCook.dimension)/2
        self.target_idx = (int(self.target_idx[0]), int(self.target_idx[1]), int(self.target_idx[2]))
        self.target_pose = np.array(domainCook.itkImage.TransformIndexToPhysicalPoint(self.target_idx))
        self.skullCrop_arr = domainCook.array
        self.rawCrop_arr = domainCook.array.copy()
        self.skullCrop_itk = domainCook.itkImage
        self.domain_shape = domainCook.dimension
        self.domainCook = domainCook
        self.p0 = np.zeros(self.skullCrop_arr.shape)

    def make_transducer(self, tran_pose, normal = l2n([0,0,0])):

        width = self.width
        ROC = self.ROC
        dx = self.dx

        ## Slicer to NIFTI coordinate
        tran_pose = np.multiply(tran_pose,  (-1, -1, 1)).astype(float)
        self.tran_pose = tran_pose

        self.tran_idx = np.array(self.skullCrop_itk.TransformPhysicalPointToIndex(tran_pose)).astype(int)

        if np.all(normal ==0):
            self.normal = (self.target_idx - self.tran_idx)/np.linalg.norm(self.target_idx - self.tran_idx)
        else:
            self.normal =l2n(normal)

        Tcenter = self.tran_idx
        Tnormal =  self.normal

        Spos = hlp.make_transducer(ROC, width, dx, Tcenter, Tnormal)
        Spos = Spos.astype(int)

        if np.any(Spos[:,0] >= self.skullCrop_arr.shape[0])\
                or np.any(Spos[:,1] >= self.skullCrop_arr.shape[1])\
                or np.any(Spos[:,2] >= self.skullCrop_arr.shape[2]):
            self.Spos = -10
            self.p0 = np.ones(self.domain_shape)*(-10)
        else:
            p0 = self.skullCrop_arr.copy()
            p0[:,:,:] = 0
            p0[Spos[:,0],Spos[:,1],Spos[:,2]] = 1
            #p0 = p0.transpose([2, 1, 0])

            self.Spos = Spos
            self.p0 = p0

            self.trans_itk = self.domainCook.makeITK(self.p0*2000, self.path+"\\transducer.nii")

    def run_simulation(self):
        start = time.time()
        print(" ")
        print(" ")
        print("################################")
        print("Start simulation")
        print("################################")
        print(" ")
        print(" ")
        print("####  Simulation specs  ####")
        print("Iso Voxel size: " + str(self.dx))

        print("CFL: " + str(self.CFL))
        print("end time: " + str(self.end_time))
        print("PPW: " + str(self.points_per_wavelength))

        ####################################################################
        # Source properties
        amplitude = self.amplitude       # source pressure [Pa]
        source_freq = self.source_freq     # frequency [Hz]

        ####################################################################
        # Material properties
        c_water = self.c_water      # [m/s]
        d_water = self.d_water      # [kg/m^3]
        a_water = self.a_water   # [Np/MHz/m]

        c_bone = self.c_bone       # [m/s]    # 2800 or 3100 m/s
        d_bone = self.d_bone       # [kg/m^3]
        a_bone_min = self.a_bone_min   # [Np/MHz/m]
        a_bone_max = self.a_bone_max  # [Np/MHz/m]
        alpha_power = self.alpha_power

        ####################################################################
        # Grid properties
        dx = self.dx
        dy = dx
        dz = dx
        grid_res = self.grid_res

        ####################################################################
        # skull array
        skullCrop_arr = self.skullCrop_arr

        ####################################################################
        # Transducer
        p0 = self.p0


        ####################################################################
        # Time step
        CFL      = self.CFL
        end_time = self.end_time
        dt       = CFL * grid_res[0] / c_water
        steps    = int(end_time / dt)


        input_filename  ='kwave_in.h5'
        output_filename ='kwave_out.h5'

        ####################################################################
        # Skull process

        grid_size = skullCrop_arr.shape
        skullCrop_arr[skullCrop_arr > 3000] = 3000
        skullCrop_arr[skullCrop_arr < 250 ] = 0

        if np.all(skullCrop_arr==0):
            skull_max = 1
        else:
            skull_max = np.max(skullCrop_arr)

        print("Skull_max test", np.max(skullCrop_arr))

        ####################################################################
        # assign skull properties depend on HU value  - Ref. Numerical evaluation, Muler et al, 2017
        PI = 1 - (skullCrop_arr/skull_max)

        ct_sound_speed = c_water*PI + c_bone*(1-PI)
        ct_density  = d_water*PI + d_bone*(1-PI)

        ct_att          = a_bone_min + (a_bone_max-a_bone_min)*np.power(PI, 0.5)
        ct_att[PI==1]   = a_water

        ###################################################################
        # assign skull properties depend on HU value  - Ref. Multi resolution, Yoon et al, 2019
        # PI = skullCrop_arr/np.max(skullCrop_arr)
        # ct_sound_speed = c_water + (2800 - c_water)*PI
        # ct_density     = d_water + (d_bone - d_water)*PI
        # ct_att         = 0 + (20 - 0)*PI

        ####################################################################
        # Assign material properties
        sound_speed     = ct_sound_speed
        density         = ct_density
        alpha_coeff_np  = ct_att

        alpha_coeff = hlp.neper2db(alpha_coeff_np/pow(2*np.pi*1e6, alpha_power), alpha_power) #[Np/MHz/m] -> [Np/(rad/s)^y/m] -> [dB/MHz/cm]

        ####################################################################
        # Define simulation input and output files
        print("## k-wave core input function")
        input_file  = KWaveInputFile(input_filename, grid_size, steps, grid_res, dt)
        output_file = KWaveOutputFile(file_name=output_filename)


        ####################################################################
        # Transducer signal
        source_signal = amplitude * np.sin((2*math.pi)*source_freq*np.arange(0.0, steps*dt, dt))


        ####################################################################
        # Open the simulation input file and fill it as usual
        with input_file as file:
            file.write_medium_sound_speed(sound_speed)
            file.write_medium_density(density)
            file.write_medium_absorbing(alpha_coeff, alpha_power)
            file.write_source_input_p(file.domain_mask_to_index(p0), source_signal, KWaveInputFile.SourceMode.ADDITIVE, c_water)

            sensor_mask = np.ones(grid_size)
            file.write_sensor_mask_index(file.domain_mask_to_index(sensor_mask))

        # Create k-Wave solver driver, which will call C++/CUDA k-Wave binary.
        # It is usually necessary to specify path to the binary: "binary_path=..."
        driver = KWaveBinaryDriver()


        # Specify which data should be sampled during the simulation (final pressure in the domain and
        # RAW pressure at the sensor mask
        driver.store_pressure_everywhere([DomainSamplingType.MAX])
        if self.recording:
            driver.store_pressure_at_sensor([SensorSamplingType.RAW])


        # Execute the solver with specified input and output files
        driver.run(input_file, output_file)
        print("## Calculation time :", time.time() - start)


        #Open the output file and generate plots from the results
        with output_file as file:

            p_max = file.read_pressure_everywhere(DomainSamplingType.MAX)
            if self.recording:
                p_raw = file.read_pressure_at_sensor(SensorSamplingType.RAW)
                p_raw = np.squeeze(p_raw).transpose([1, 0])
                time_step = p_raw.shape[1]
                #p_raw = np.flip(p_raw)
                p_raw = p_raw.flatten()
                p_raw = np.reshape(p_raw, (self.domain_shape[0], self.domain_shape[1], self.domain_shape[2], time_step))
                p_raw = p_raw.transpose([2, 1, 0, 3])
                self.p_raw = p_raw

            self.p_max = p_max
            result_itk = self.domainCook.makeITK(p_max, self.path+"\\forward.nii")
            self.result_itk = result_itk

        return result_itk

    # Convert target as back propagation source
    def back_propagation_source(self):
        ####################################################################
        # Target point is source for back propagation
        # target_idx = self.target_idx
        p0 = np.zeros((self.domain_shape))
        p0[self.target_idx[0], self.target_idx[1], self.target_idx[2]] = 1
        self.p0 = p0

    # Run back propagation
    def run_backpropagation(self):

        start = time.time()
        print(" ")
        print(" ")
        print("################################")
        print("Start Back propagation")
        print("################################")
        print(" ")
        print(" ")
        print("####  Simulation specs  ####")
        print("Iso Voxel size: " + str(self.dx))

        print("CFL: " + str(self.CFL))
        print("end time: " + str(self.end_time))
        print("PPW: " + str(self.points_per_wavelength))

        input_filename  ='kwave_in.h5'
        output_filename ='kwave_out.h5'

        ####################################################################
        # Source properties
        amplitude = self.amplitude       # source pressure [Pa]
        source_freq = self.source_freq     # frequency [Hz]

        ####################################################################
        # Material properties
        c_water = self.c_water      # [m/s]
        d_water = self.d_water      # [kg/m^3]
        a_water = self.a_water   # [Np/MHz/cm]

        c_bone = self.c_bone       # [m/s]    # 2800 or 3100 m/s
        d_bone = self.d_bone       # [kg/m^3]
        a_bone_min = self.a_bone_min   # [Np/MHz/cm]
        a_bone_max = self.a_bone_max  # [Np/MHz/cm]
        alpha_power = self.alpha_power

        ####################################################################
        # Grid properties
        dx = self.dx
        dy = dx
        dz = dx
        grid_res = self.grid_res

        ####################################################################
        # skull array
        skullCrop_arr = self.skullCrop_arr

        ####################################################################
        # Time step
        CFL      = self.CFL
        end_time = self.end_time
        dt       = CFL * grid_res[0] / c_water
        steps    = int(end_time / dt)
        self.dt = dt


        ####################################################################
        # Back propagation source
        p0 = self.p0
        p0_idx = np.squeeze(np.where(p0 == 1))
        self.back_source.append(p0_idx)


        # normalize HU value
        grid_size = skullCrop_arr.shape
        skullCrop_arr[skullCrop_arr > 3000] = 3000
        skullCrop_arr[skullCrop_arr < 250 ] = 0


        ####################################################################
        # assign skull properties depend on HU value  - Ref. Numerical evaluation, Muler et al, 2017
        print("Skull_max", np.max(skullCrop_arr))
        PI = 1 - (skullCrop_arr/np.max(skullCrop_arr))
        ct_sound_speed = c_water*PI + c_bone*(1-PI)
        ct_density  = d_water*PI + d_bone*(1-PI)

        ct_att          = a_bone_min + (a_bone_max-a_bone_min)*np.power(PI, 0.5)
        ct_att[PI==1]   = a_water

        ###################################################################
        # For back propagation kill the attenuation
        ct_att[:,:,:] = 0

        ###################################################################
        # assign skull properties depend on HU value  - Ref. Multi resolution, Yoon et al, 2019
        # PI = skullCrop_arr/np.max(skullCrop_arr)
        # ct_sound_speed = c_water + (2800 - c_water)*PI
        # ct_density     = d_water + (d_bone - d_water)*PI
        # ct_att         = 0 + (20 - 0)*PI


        ####################################################################
        # Assign material properties
        sound_speed     = ct_sound_speed
        density         = ct_density
        alpha_coeff_np  = ct_att


        alpha_coeff = hlp.neper2db(alpha_coeff_np/pow(2*np.pi*1e6, alpha_power), alpha_power) #[Np/MHz/m] -> [Np/(rad/s)^y/m] -> [dB/MHz/cm]

        ####################################################################
        # Define simulation input and output files
        print(" ")
        print(" ")
        print("## k-wave core input function")
        input_file  = KWaveInputFile(input_filename, grid_size, steps, grid_res, dt)
        output_file = KWaveOutputFile(file_name=output_filename)

        ####################################################################
        # Transducer signal

        period = 1/source_freq
        single_pulse_step = np.ceil(period/dt).astype(int)
        source_signal = amplitude * np.sin((2*math.pi)*source_freq*np.arange(0.0, steps*dt, dt))
        source_signal[single_pulse_step:] = 0

        ####################################################################
        # Open the simulation input file and fill it as usual
        with input_file as file:
            file.write_medium_sound_speed(sound_speed)
            file.write_medium_density(density)
            file.write_medium_absorbing(alpha_coeff, alpha_power)
            file.write_source_input_p(file.domain_mask_to_index(p0), source_signal, KWaveInputFile.SourceMode.ADDITIVE, c_water)

            sensor_mask = np.ones(grid_size)
            file.write_sensor_mask_index(file.domain_mask_to_index(sensor_mask))

        # Create k-Wave solver driver, which will call C++/CUDA k-Wave binary.
        # It is usually necessary to specify path to the binary: "binary_path=..."
        driver = KWaveBinaryDriver()


        # Specify which data should be sampled during the simulation (final pressure in the domain and
        # RAW pressure at the sensor mask
        driver.store_pressure_everywhere([DomainSamplingType.MAX])
        if self.recording:
            driver.store_pressure_at_sensor([SensorSamplingType.RAW])


        # Execute the solver with specified input and output files
        driver.run(input_file, output_file)
        print(" ")
        print(" ")
        print("## Calculation time of Back propagation :", time.time() - start)


        #Open the output file and generate plots from the results
        with output_file as file:
            if self.recording:
                p_raw_raw = file.read_pressure_at_sensor(SensorSamplingType.RAW)
                p_raw = np.squeeze(p_raw_raw).transpose([1,0])

                del p_raw_raw

                time_step = p_raw.shape[1]
                #p_raw = np.flip(p_raw,axis=0)
                p_raw = np.ravel(p_raw)
                p_raw = np.reshape(p_raw, (self.domain_shape[2], self.domain_shape[1], self.domain_shape[0], time_step))
                p_raw = p_raw.transpose([2, 1, 0, 3])
                self.p_raw = p_raw
                self.p_max = np.max(p_raw, axis=3)


            else:
                p_max = file.read_pressure_everywhere(DomainSamplingType.MAX)
                self.p_max = p_max

            resultCook = niiCook()
            resultCook.readITK(self.skullCrop_itk)
            result_itk = resultCook.makeITK(self.p_max, self.path+"\\back.nii")

        del output_file

        return result_itk

    # Set ROI and calculate Amp and Phase
    def make_ROI(self, plane = False):

        print("## Calculate ROI")

        focal_length = self.focal_length
        skull_arr = self.skullCrop_arr
        dx = self.dx
        dt = self.dt
        source_freq = self.source_freq
        p_raw = self.p_raw


        headCook = niiCook()
        headCook.readITK(self.skullCrop_itk)
        head, _ = headCook.segmentationMask(1)
        head = -(head-1)


        target = self.target_idx

        idx = np.where(skull_arr > 250)
        temp = np.argmin(np.sqrt(
            np.power(idx[0] - target[0], 2) + np.power(idx[1] - target[1], 2) + np.power(idx[2] - target[2], 2)))
        min_dist_idx = np.array((idx[0][temp], idx[1][temp], idx[2][temp]))

        idx_normal = (min_dist_idx - target) / np.linalg.norm(min_dist_idx - target)
        length_idx = np.round(focal_length * 0.001 / dx)

        initial_idx = (length_idx * idx_normal + target).astype(int)

        shape = np.array(skull_arr.shape)
        ROI = np.ones(shape)

        # Plane equation using normal and point
        x_arr = np.arange(0, shape[0])
        y_arr = np.arange(0, shape[1])
        z_arr = np.arange(0, shape[2])

        my, mx, mz = np.meshgrid(y_arr, x_arr, z_arr)

        cont = idx_normal[0] * target[0] + idx_normal[1] * target[1] + idx_normal[2] * target[2]
        plane_cal = mx * idx_normal[0] + my * idx_normal[1] + mz * idx_normal[2] - cont
        plane_cal = np.round(plane_cal, 1)

        plane_cal[plane_cal > 0] = 1
        plane_cal[plane_cal < 0] = 0
        plane_cal = plane_cal.astype(int)

        max_b = hlp.makeSphere(shape, focal_length/(dx*1000)*1.6, target)
        min_b = hlp.makeSphere(shape, focal_length/(dx*1000)*0.7, target)
        limit = max_b-min_b

        ROI = ROI*limit
        ROI = ROI*head
        if plane:
            ROI = ROI*plane_cal

        ROI_idx = np.array(np.where(ROI == 1))
        ROI_idx = ROI_idx.transpose()

        times = np.linspace(1, np.int(p_raw.shape[3]), np.int(p_raw.shape[3]), endpoint=True) * dt
        period = 1 / source_freq

        BP_Phase = np.zeros(shape)
        BP_Amp = np.zeros(shape)
        BP_step = np.zeros(shape)

        BP_Phase, BP_Amp, BP_step = hlp.make_ROI_fast(ROI_idx, p_raw, times, BP_Phase, BP_Amp, BP_step,period)

        BP_Amp = 100*BP_Amp/BP_Amp.max()
        #BP_Amp = BP_Amp+BP_step

        self.domainCook.makeITK(BP_Phase, self.path+"\\BP_Phase.nii")
        self.domainCook.makeITK(BP_Amp, self.path+"\\BP_Amp.nii")

        self.initial_idx = initial_idx
        self.ROI = ROI
        self.ROI_idx = ROI_idx
        self.PHASE.append(BP_Phase)
        self.AMP.append(BP_Amp)

    # Set ROI and calculate Amp/Phase
    def calculateScore(self, Input_data):

        Input_data = l2n(Input_data)

        TCenter_normalized = Input_data[:3]
        Tnormal = Input_data[3:]
        Tnormal = Tnormal/np.linalg.norm(Tnormal)

        ROI_idx = self.ROI_idx
        TCenter = TCenter_normalized.copy()

        x_range = l2n([ROI_idx[:, 0].min(), ROI_idx[:, 0].max()])
        y_range = l2n([ROI_idx[:, 1].min(), ROI_idx[:, 1].max()])
        z_range = l2n([ROI_idx[:, 2].min(), ROI_idx[:, 2].max()])

        TCenter[0] =  TCenter_normalized[0]*(x_range.max()- x_range.min()) + x_range.min()
        TCenter[1] =  TCenter_normalized[1]*(y_range.max()- y_range.min()) + y_range.min()
        TCenter[2] =  TCenter_normalized[2]*(z_range.max()- z_range.min()) + z_range.min()

        TCenter = TCenter.astype(int)

        ## Check Normal vector

        angle = []
        for i in range(len(self.back_source)):
            back_target_idx = self.back_source[i]
            standard_vector = l2n(back_target_idx) - l2n(TCenter)

            standard_vector = standard_vector / np.linalg.norm(standard_vector)
            dot_product = np.dot(Tnormal, standard_vector)
            angle.append(np.abs(np.rad2deg(np.arccos(dot_product))))

        if angle[0]>20:
            score = 0
            self.restart = self.restart + 1
            return score

        score, Spos = hlp.score_fast(TCenter, Tnormal, self.PHASE, self.AMP, self.skullCrop_arr, self.width, self.ROC, self.dx)
        self.gather_score.append(score)
        self.restart  = self.restart+1

        if score != 0:

            if self.optimizer_check==0:
                print("Optimizer enter the orbit")
                self.optimizer_check = 1

            point = self.skullCrop_itk.TransformIndexToPhysicalPoint((int(TCenter[0]), int(TCenter[1]), int(TCenter[2])))
            point = l2n(point)*l2n([-1,-1,1])

            final_data = np.zeros(7)
            final_data[:3] = point
            final_data[3:6] = Tnormal
            final_data[-1] = score

            self.gather_point.append(final_data)

        return -score

    # Differential evolution optimizer
    def Score_optimizer(self):

        print(" ")
        print(" ")
        print("################################")
        print("Start Optimizer")
        print("################################")
        print(" ")
        print(" ")

        self.set_trans_num()

        try:
            bounds = self.cut_plane_option
        except:
            bounds = [(0, 1), (0, 1), (0, 1), (-1, 1), (-1, 1), (-1, 1)]

        a = time.time()

        ## while loop for poor initial values
        while True:
            result = differential_evolution(self.calculateScore, bounds)#, updating='deferred', workers=4)
            check = l2n(self.gather_score)
            if np.any(check != 0):
                break
            if self.restart > 20000:
                print("There is no proper position for transducer, re-make ROI or sonication condition")
                break
            print("Poor initial values // Restart optimizer")

        b = time.time()
        print("Computing time for optimizer: ", b-a)

        ROI_idx = self.ROI_idx
        TCenter_normalized = result.x[:3]
        TCenter = TCenter_normalized.copy()
        Tnormal = result.x[3:]
        Tnormal = l2n(Tnormal)/np.linalg.norm(l2n(Tnormal))

        x_range = l2n([ROI_idx[:, 0].min(), ROI_idx[:, 0].max()])
        y_range = l2n([ROI_idx[:, 1].min(), ROI_idx[:, 1].max()])
        z_range = l2n([ROI_idx[:, 2].min(), ROI_idx[:, 2].max()])

        TCenter[0] =  TCenter_normalized[0]*(x_range.max()- x_range.min()) + x_range.min()
        TCenter[1] =  TCenter_normalized[1]*(y_range.max()- y_range.min()) + y_range.min()
        TCenter[2] =  TCenter_normalized[2]*(z_range.max()- z_range.min()) + z_range.min()

        optimalPos_idx = TCenter.astype(int)
        self.optimalPos_idx = optimalPos_idx

        optimalPos = self.skullCrop_itk.TransformIndexToPhysicalPoint((int(optimalPos_idx[0]), int(optimalPos_idx[1]), int(optimalPos_idx[2])))
        optimalPos = np.round(optimalPos*l2n([-1,-1,1]), 2)

        self.optimalPos = optimalPos
        self.optialNormal = Tnormal

        point_normal_np = np.squeeze(l2n(self.gather_point))
        np.save(self.path + "\\point_normal_conversion.npy", point_normal_np)
        np.save(self.path + "\\point_normal_conversion.npy", point_normal_np)
        np.savetxt(self.path + "\\point_normal_conversion.txt", point_normal_np, fmt='%.3f', delimiter=',')

        print("Finish optimize !!")

    def set_trans_num(self):
        self.tran_num = 0
        self.cook = niiCook()
        self.cook.readITK(self.skullCrop_itk)
        self.gather_point = []
        self.gather_score = []
        self.restart = 0

    # Final function to find optimal position
    def findOptimalPosition(self, source = l2n([-100,-100,-100]), cut_plane=False):


        self.recording = True
        a = time.time()

        # if is ture the orientation of the transducer also going to be optimized
        if np.all(source==-100):
            self.back_propagation_source()
            self.run_backpropagation()
            self.make_ROI(cut_plane)
            self.Score_optimizer()
        else:
            source[:, 0] = -source[:, 0]
            source[:, 1] = -source[:, 1]

            for i in range(source.shape[0]):
                point = self.skullCrop_itk.TransformPhysicalPointToIndex(source[i,:])
                self.back_source.append(point)
                self.p0 = np.zeros(self.domain_shape)
                self.p0[int(point[0]), int(point[1]), int(point[2])] = 1
                self.run_backpropagation()
                self.make_ROI()

                del self.p_raw

            self.Score_optimizer()

            del self.PHASE
            del self.AMP

        b = time.time()
        print("Computing time whole process", b-a)
        print("T position:", self.optimalPos, " T normal:", self.optialNormal)

        final = np.zeros((2,3))
        final[0,:] = self.optimalPos
        final[1,:] = self.optialNormal

        np.save(self.path+"\\optimal_position", final)

        V1 = str('{:.3f}'.format(final[0,0]) + ' {:.3f}'.format(final[0,1]) + ' {:.3f}'.format(final[0,2]))
        f = open(os.path.join(self.path, 'Optimal position.txt'), 'w')
        f.write(V1)
        f.close()

        V1 = str('{:.3f}'.format(final[1,0]) + ' {:.3f}'.format(final[1,1]) + ' {:.3f}'.format(final[1,2]))
        f = open(os.path.join(self.path, 'Optimal normal.txt'), 'w')
        f.write(V1)
        f.close()
        f.close()

        self.recording = False

        return self.optimalPos, self.optialNormal

