import gzip
import json
import pathlib
from rdkit import Chem

from gufe import (
    AlchemicalNetwork,
    ChemicalSystem,
    Transformation,
    SmallMoleculeComponent,
)
from gufe.tokenization import JSON_HANDLER
from openff.toolkit import Molecule
from openff.units import unit
from pontibus.protocols.solvation import ASFEProtocol
from pontibus.protocols.solvation.settings import PackmolSolvationSettings
from pontibus.components import ExtendedSolventComponent


def get_water_settings():
    # The settings here are effectively the "fast" settings
    # shown in the validation.
    settings = ASFEProtocol.default_settings()
    # Because it's Alchemiscale, you set protocol_repeats to 1 and then
    # run the Transformation task multiple times to get repeats.
    # Locally, the recommendation would be to set this to 3 so that you can
    # get a standard deviation uncertainty. It's not super necessary since
    # SFEs converge well, but hey with Alchemiscale why not?!
    settings.protocol_repeats = 1
    settings.solvent_forcefield_settings.forcefields = [
        # To use a custom force field, just pass an OFFXML string
        # just like you would to openff.toolkit.ForceField
        "openff-2.0.0.offxml",
        "tip3p.offxml",
    ]
    settings.vacuum_forcefield_settings.forcefields = [
        "openff-2.0.0.offxml",  # as above
    ]
    # This defines the compute platform to use, usually on alchemiscale you'll
    # want to just set it to CUDA so you can fail fast if the GPU isn't available
    settings.vacuum_engine_settings.compute_platform = "CUDA"
    settings.solvent_engine_settings.compute_platform = "CUDA"
    # For the water solvation, we set a dodecahedron around the solute with
    # a minimum of 1.5 nm solvent padding. In our tests this works for freesolv.
    # In some cases, especially with ligands that can unfold, you may need to
    # bump this up.
    settings.solvation_settings = PackmolSolvationSettings(
        box_shape="dodecahedron",
        assign_solvent_charges=False,
        solvent_padding=1.5 * unit.nanometer,
    )
    # Below are the default lambda & replica settings, so you don't have to
    # actually set them, but if you want to change things, you can alter them
    # by defining them this way. Note: you have to update n_replica to match
    # the number of lambda windows (and all lambda window lists must be of the same length).
    settings.lambda_settings.lambda_elec = [
        0.0, 0.25, 0.5, 0.75, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    ]
    settings.lambda_settings.lambda_vdw = [
        0.0, 0.0, 0.0, 0.0, 0.0,
        0.12, 0.24, 0.36, 0.48, 0.6, 0.7, 0.77, 0.85, 1.0,
    ]
    settings.lambda_settings.lambda_restraints = [
        0.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    ]
    settings.vacuum_simulation_settings.n_replicas = 14
    settings.solvent_simulation_settings.n_replicas = 14
    # This set the time per replica exchange, the default is 1 ps but
    # hurts performance. I would recommend 2.5 ps
    settings.solvent_simulation_settings.time_per_iteration = 2.5 * unit.picosecond
    settings.vacuum_simulation_settings.time_per_iteration = 2.5 * unit.picosecond
    # Below are the default simulation lengths we use in Pontibus,
    # so you don't need to set them. However, you can do so manually
    # This is the pre-alchemical equilibration lengths
    # NVT equilibration -> NPT equilibration -> NPT "production" (more equilibration)
    # In vacuum, we set the NVT equilibration to None since it's all gas phase
    settings.solvent_equil_simulation_settings.equilibration_length_nvt = 0.5 * unit.nanosecond
    settings.solvent_equil_simulation_settings.equilibration_length = 0.5 * unit.nanosecond
    settings.solvent_equil_simulation_settings.production_length = 9.5 * unit.nanosecond
    settings.vacuum_equil_simulation_settings.equilibration_length_nvt = None
    settings.vacuum_equil_simulation_settings.equilibration_length = 0.2 * unit.nanosecond
    settings.vacuum_equil_simulation_settings.production_length = 0.5 * unit.nanosecond
    # This is the alchemical equilibration length
    settings.solvent_simulation_settings.equilibration_length = 1.0 * unit.nanosecond
    settings.vacuum_simulation_settings.equilibration_length = 0.5 * unit.nanosecond
    # This is the alchemical production length
    settings.solvent_simulation_settings.production_length = 2.0 * unit.nanosecond
    settings.vacuum_simulation_settings.production_length = 2.0 * unit.nanosecond
    return settings


def get_transformation(smc, solvent):

    settings = get_water_settings()

    stateA = ChemicalSystem({"solute": smc, "solvent": solvent})
    stateB = ChemicalSystem({"solvent": solvent})
    protocol = ASFEProtocol(settings=settings)
    return Transformation(
        stateA=stateA, stateB=stateB, mapping=None, protocol=protocol, name=stateA.name
    )


def run(ligands: pathlib.Path):
    smcs = [
        SmallMoleculeComponent(mol)
        for mol in Chem.SDMolSupplier(ligands, removeHs=False)
    ]

    transformations = []
    for smc in smcs:
        transformations.append(
            get_transformation(smc, ExtendedSolventComponent())
        )

    alchemical_network = AlchemicalNetwork(transformations)
    alchemical_network.to_json("alchemical_network.json")


if __name__ == "__main__":
    ligands = pathlib.Path("fsolv_am1bccelf10.sdf")
    run(ligands)
