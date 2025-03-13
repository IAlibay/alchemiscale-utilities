import csv
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


def get_nonwater_settings():
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
    ]
    settings.vacuum_forcefield_settings.forcefields = [
        "openff-2.0.0.offxml",  # as above
    ]
    settings.vacuum_engine_settings.compute_platform = "CUDA"
    settings.solvent_engine_settings.compute_platform = "CUDA"
    settings.solvation_settings = PackmolSolvationSettings(
        # In our tests 750 gave quasi equivalent results to the 1999 used in the Sage
        # benchmarks
        number_of_solvent_molecules=750,
        box_shape="cube",
        # We set assign_solvent_charges to True because we don't have LibraryCharges.
        # If False it will only attempt to use LibraryCharges.
        # Note that if True and you don't have any charges on the SmallMoleculeComponent
        # passed to ExtendedSolventComponent, the Protocol will attempt to automatically
        # assign partial charges (default is AmberTools am1bcc, but it's controllable
        # using `partial_charge_settings`.
        assign_solvent_charges=True,
        solvent_padding=None,
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
    settings.solvent_simulation_settings.production_length = 10.0 * unit.nanosecond
    settings.vacuum_simulation_settings.production_length = 2.0 * unit.nanosecond
    return settings


def get_transformation(system):

    settings = get_nonwater_settings()

    # An SFE transformation in GUFE formalism is defined as
    # going from a solute + solvent (stateA) to just solvent (stateB)
    stateA = system
    stateB = ChemicalSystem({"solvent": system.components["solvent"]})
    protocol = ASFEProtocol(settings=settings)
    return Transformation(
        stateA=stateA, stateB=stateB, mapping=None, protocol=protocol, name=stateA.name
    )


def smc_dict(ligands: pathlib.Path):
    molecules = {}

    rdmols = Chem.SDMolSupplier(ligands, removeHs=False)

    for mol in rdmols:
        smiles = mol.GetProp("smiles")
        molecules[smiles] = SmallMoleculeComponent(mol)

    return molecules


def get_chemical_systems(smcs, csv_benchmark_data: pathlib.Path):
    """
    Using the benchmark data file, create a set of ChemicalSystems
    that contain the solute and solvent Components.
    """

    benchmark_data = []

    with open(csv_benchmark_data, newline="") as csvfile:
        reader = csv.reader(csvfile, delimiter=",", quotechar="|")
        header = next(reader)

        for row in reader:
            benchmark_data.append(row)

    systems = []
    for entry in benchmark_data:
        # ExtendedSolventComponent is a special case of SolventComponent
        # it takes a SmallMoleculeComponent on construction and retains
        # its properties. Technically you could also just use a standard
        # SolventComponent, but this allows you to define the solvent's
        # conformer before packing, and also pass through user charges.
        solvent = ExtendedSolventComponent(solvent_molecule=smcs[entry[4]])
        solute = smcs[entry[5]]

        csystem = ChemicalSystem(
            {
                "solute": solute,
                "solvent": solvent,
            },
            name=f"{entry[5]} | {entry[4]}",
        )
        systems.append(csystem)

    return systems


def run(ligands: pathlib.Path, csv_benchmark_data: pathlib.Path):
    """
    Create an alchemical network.
    """
    smcs = smc_dict(ligands)

    chemical_systems = get_chemical_systems(smcs, csv_benchmark_data)

    transformations = []
    for chemical_system in chemical_systems:
        transformations.append(get_transformation(chemical_system))

    alchemical_network = AlchemicalNetwork(transformations)
    alchemical_network.to_json("alchemical_network.json")


if __name__ == "__main__":
    ligands = pathlib.Path("mnsol_am1bccelf10.sdf")
    csv_benchmark_data = pathlib.Path("full_results_mnsol_2_0_0.csv")
    run(ligands, csv_benchmark_data)
