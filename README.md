# Find optimal location of the transducer for tFUS

This repository is the implementation of the paper
##### Differential evolution method to find optimal location of a single-element transducer for transcranial focused ultrasound therapy, Computer Methods and Programs in Biomedicine, 2022, 106777, ISSN 0169-2607, https://doi.org/10.1016/j.cmpb.2022.106777.

#### Objective
The large mismatch of acoustic properties between the skull and water can disrupt and shift the acoustic focus in the brain. 
In this paper, we present a numerical method to find the optimal location of a single-element FUS transducer, which creates focus on the target region. 

#### Methods
The aberrations of the wave phase and amplitude induced by the presence of the skull were calculated through a time-reversal simulation of the emitting ultrasound at the target point. The score function, which represents the superposition of acoustic waves according to the relative phase difference and pressure transmissibility, was calculated for the given transducer location. The optimal location of the FUS transducer is determined by maximizing the score function using the differential evolution (DE) optimization method. 


## Structure
    help_function      --> Folder for help function  
    kwave_core         --> Folder for k-Wave core (e.g., .exe and .dll)
    kwave_function     --> Folder for python wapper (e.g., Matlab to Python) author by Filip Vaverka
    Test_data          --> Test skull data 
    
    simulation_function.py   --> main simulation function 
    Example.py               --> Use of this method 

 ## Process
 
 #### 1. Set transducer spec (e.g., ROC, width, FF, and focal length)
 
 #### 2. Set sonication spec  (e.g, end_time, CFL, and PPW etc)

 #### 3. Pre-process (Crop and Resample --> make simulation domain)
 + Using the CT image, the simulation domain with the skull was cropped and resampled.
 + The pre-process was performed using "Simpleitk" resampling strategy (e.g., nearest neighbor)
 
 #### 4. Find optimal position of the transducer
> 4-1. Time-reversal simulation was performed. The target point was set as the virtual source.  
>
> 4-2. The transmissibility and phase profile was evaluated using the time-reversal simulation results.
>
><img src="https://user-images.githubusercontent.com/42193020/158530006-e7a6cb56-05e9-4198-b0f2-6ad0a4a3fc9d.png" width="500" height="450"/>
>
> 4-3. Using this equation, the score was calculated depending on the transducer location
>
><img src="https://user-images.githubusercontent.com/42193020/158530402-0f9a607a-9eb6-408a-830c-77ff6db2aea7.PNG" width="400" height="100"/>
>
> 4-4. The differential evolution algorithm was used to find the maximum score value according to the transducer location. 


 #### 5. Make transducer 
 + On the simulation domain the transducer was made depending on the given position and orientation of the transducer.
 
 #### 6. Run forward simulation

 ## How to start
 + Create the environment using .yaml file. In ananconda prompte type this
  
        conda env create --file environment.yaml
        conda activate Simulation_env
 
 + Then, perform the "Example.py".

 ## Data management
 
 #### + In this package, all 3D grid data (i.e., skull and simulation result) was saved as .nii file 
  + .nii file can save the 3D data with origin, spacing, and volume value (HU)
  + Easy to plot using medical image platform e.g., 3D Slicer
  
 #### + In result dir, saved file like this
    # Time-reversal simulation results 
    back.nii            --> Time-reversal simulation result
    BP_Amp.nii          --> Amplitude map from time-reversal simulation 
    BP_Phase.nii        --> Phase map from time-reversal simulation

    # Forward simulation results  
    skullCrop_itk.nii   --> Pre-processed skull image (simulation domain)
    Transudcer.nii      --> Discritized transducer geometry at simulation domain
    forward.nii         --> forward acoustic simulation result 

## Contact
This package was developed by TY Park from Korea Institute Science and Technology school (KIST school)
E-mail: pty0220@kist.re.kr
