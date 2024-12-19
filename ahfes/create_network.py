import click
import openfe
import gufe
from gufe import tokenization
import pathlib
from openff.toolkit import Molecule
from openff.toolkit.utils.toolkits import OpenEyeToolkitWrapper
from openff.units import unit
import openfe
from openfe import SmallMoleculeComponent
from openfe.protocols.openmm_afe import AbsoluteSolvationProtocol
from openfe.utils import without_oechem_backend
import numpy as np
import json


def get_smiles(filename):
    """
    Get a list of smiles from an input file.
    """
    # get a list of smiles
    with open(filename, 'r') as f:
        data = f.read().splitlines()
    return data


def gen_off_molecule(smi):
    """
    Generate an openff molecule from an input smiles
    """
    m = Molecule.from_smiles(smi)
    m.generate_conformers()
    m.assign_partial_charges(
        'am1bccelf10',
        use_conformers=m.conformers,
        toolkit_registry=OpenEyeToolkitWrapper(),
    )
    m.name = smi
    return m


def get_small_molecule_components(
    filename: str
) -> list[SmallMoleculeComponent]:
    """
    Get a list of SmallMoleculeComponents

    Parameters
    ----------
    filename : str
      A string to the filename with the smiles.

    Returns
    -------
    smcs : list[SmallMoleculeComponent]
      A list of SmallMoleculeComponent for each ligand
      in the input smiles.

    What this does:
    ---------------
    * Loop through the input list of smiles.
    * Generate an OpenFF molecule for each entry
    * Turn the molecule into an openfe SmallMolculeComponent (smc)
    * Return a list of the smcs)
    """
    smiles = get_smiles(filename)

    smcs = []

    for smi in smiles:
        offmol = gen_off_molecule(smi)
        comp = SmallMoleculeComponent.from_openff(offmol, name=offmol.name)
        smcs.append(comp)

    return smcs


def get_settings():
    """
    Return some settings for the AbsoluteSolvationProtocol
    """
    settings = AbsoluteSolvationProtocol.default_settings()
    # Always set the repeats to 1 for alchemiscale
    settings.protocol_repeats = 1
    # Thermodynamic settings
    settings.thermo_settings.temperature = 298.15 * unit.kelvin
    settings.thermo_settings.pressure = 1 * unit.bar
    # Force field settings
    settings.solvent_forcefield_settings.nonbonded_method = 'pme'
    settings.solvent_forcefield_settings.hydrogen_mass = 1.00784
    settings.solvent_forcefield_settings.small_molecule_forcefield = 'openff-2.2.1'
    settings.solvent_forcefield_settings.forcefields = ['amber/tip3p_standard.xml']
    settings.vacuum_forcefield_settings.nonbonded_method = 'nocutoff'
    settings.vacuum_forcefield_settings.hydrogen_mass = 1.00784
    settings.vacuum_forcefield_settings.small_molecule_forcefield = 'openff-2.2.1'
    # Solvation settings
    settings.solvation_settings.solvent_padding = None
    settings.solvation_settings.number_of_solvent_molecules = 1000
    # Integrator settings
    settings.integrator_settings.timestep = 2 * unit.femtosecond
    settings.integrator_settings.barostat_frequency = 25 * unit.timestep
    # Non-alchemical Equilibration settings (you do this first)
    settings.solvent_equil_simulation_settings.equilibration_length_nvt = 100 * unit.picosecond
    settings.solvent_equil_simulation_settings.equilibration_length = 100 * unit.picosecond
    settings.solvent_equil_simulation_settings.production_length = 100 * unit.picosecond
    settings.vacuum_equil_simulation_settings.equilibration_length_nvt = 0 * unit.picosecond # Vacuum != NVT
    settings.vacuum_equil_simulation_settings.equilibration_length = 100 * unit.picosecond
    settings.vacuum_equil_simulation_settings.production_length = 100 * unit.picosecond
    # Alchemical Equilibration settings (then you run this)
    settings.solvent_simulation_settings.equilibration_length = 200 * unit.picosecond
    settings.vacuum_simulation_settings.equilibration_length = 200 * unit.picosecond
    # Alchemical Production settings (then you sample from this)
    settings.solvent_simulation_settings.production_length = 2000 * unit.picosecond
    settings.vacuum_simulation_settings.production_length = 2000 * unit.picosecond
    # Set the exchange rates
    settings.solvent_simulation_settings.time_per_iteration = 1 * unit.picosecond
    settings.vacuum_simulation_settings.time_per_iteration = 1 * unit.picosecond
    # Set the lambda schedule (note these are reversed from what evaluator does!)
    settings.lambda_settings.lambda_elec = [
        0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0
    ]
    settings.lambda_settings.lambda_vdw = [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35,
        0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0
    ]
    settings.lambda_settings.lambda_restraints = [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    ]
    # Set the number of replicas
    settings.vacuum_simulation_settings.n_replicas = 26
    settings.solvent_simulation_settings.n_replicas = 26
    return settings


def get_solvent_component(ion_concentration: unit.Quantity = 0.0*unit.molar):
    return openfe.SolventComponent(ion_concentration=ion_concentration)


def _get_stateB(solvent_component) -> openfe.ChemicalSystem:
    return openfe.ChemicalSystem({'solvent': solvent_component})


def _get_stateA(
    small_molecule_component,
    solvent_component
) -> openfe.ChemicalSystem:
    return openfe.ChemicalSystem(
        {'ligand': small_molecule_component, 'solvent': solvent_component}
    )


def get_alchem_network(smcs, solvent_comp, protocol):
    """
    Create a transformation network from all the input ligands
    """
    transformations = []
    for smc in smcs:
        stateA = _get_stateA(smc, solvent_comp)
        stateB = _get_stateB(solvent_comp)
        t = openfe.Transformation(
            stateA=stateA, stateB=stateB,
            mapping=None,
            protocol=protocol,
            name=smc.name
        )
        transformations.append(t)

    return openfe.AlchemicalNetwork(transformations)

@click.command
@click.option(
    '--input_filename',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    help="Path to the input file of smiles",
)
@click.option(
    '--network_filename',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    help="File location where the Alchemical Network should be written to",
)
def run(input_filename, network_filename):
    # small molecule components
    # Here is where you should edit things to pass in whatever serialized
    # form of an OFF molecule that you want!
    smcs = get_small_molecule_components(input_filename)

    # solvent component
    solvent_comp = get_solvent_component()

    # Simulation settings
    settings = get_settings()

    # Create a Protocol object
    protocol = AbsoluteSolvationProtocol(settings=settings)

    # Create an Alchemical Network
    network = get_alchem_network(smcs, solvent_comp, protocol)

    # Write out the alchemical network
    with open(network_filename, 'w') as f:
        json.dump(
            network.to_dict(),
            f,
            cls=tokenization.JSON_HANDLER.encoder
        )


if __name__ == "__main__":
    run()

