import click
import csv
import os
import pathlib
import numpy as np
from openff.units import unit
import pathlib
from typing import Optional
from alchemiscale import AlchemiscaleClient, Scope, ScopedKey


def _get_average_and_stdevs(estimates) -> tuple[unit.Quantity, unit.Quantity]:
    """
    Get the average and stdev from a series
    of estimates.

    Parameters
    ----------
    estimates : list[unit.Quantity]
      A list of dG estimates for each repeat.

    Returns
    -------
    avg : unit.Quantity
      The average dG value.
    stdev : unit.Quantity
      The standard deviation of all estimates.
    """
    u = estimates[0].u
    dGs = [i.to(u).m for i in estimates]

    if len(dGs) > 3:
        print("incomplete set")

    avg = np.average(dGs) * u
    stdev = np.std(dGs) * u

    return avg, stdev


def _process_dagresults(
    dag_results
) -> tuple[Optional[unit.Quantity], Optional[unit.Quantity]]:
    """
    Process a list of ProtocolDAGResults and get the average dG and error.

    If the list is empty, returns ``None, None``.

    Parameters
    ----------
    dag_results : list[ProtocolDAGResult]
      A list of ProtocolDAGResult for a transformation.

    Returns
    -------
    dG : Optional[unit.Quantity]
      The average free energy for a transformation.
    err : Optional[unit.Quantity]
      The standard deviation in the free energy estimate between multiple
      repeats.
    """

    if len(dag_results) == 0:
        return None, None

    dG = {'solvent': [], 'vacuum': []}

    for dresult in dag_results:
        for result in dresult.protocol_unit_results:
            if result.ok():
                dG[result.outputs['simtype']].append(
                    result.outputs['unit_estimate']
                )

    vac_dG, vac_err = _get_average_and_stdevs(dG['vacuum'])
    sol_dG, sol_err = _get_average_and_stdevs(dG['solvent'])

    dG = vac_dG - sol_dG
    err = np.sqrt(vac_err**2 + sol_err**2)

    return dG, err


def _write_results(results, results_file) -> None:
    """
    Write out a tab separate list of results for each transformation.

    If the transformation results are not present, writes ``None``.

    Parameters
    ----------
    results : dict[str, dict[str, unit.Quantity]]
      A dictionary keyed by transformation names with each entry
      containing a list of dG and stdev values for each transformation.
    results_file : pathlib.Path
      A path to the file where the results will be written.
    """
    with open(results_file, 'w') as f:
        header = "solute\tsolvent"
        header += f"\tcalc_dG (kcal/mol)\tcalc_err (kcal/mol)"
        header += f"\texp_dG (kcal/mol)\texp_err (kcal/mol)"
        header += f"\tref_dG (kcal/mol)\tref_err (kcal/mol)\n"
        f.write(header)

        for r in results.keys():
            if results[r]['calc_dG'] is None:
                f.write(f"{r[0]}\t{r[1]}\tNone\tNone\tNone\tNone\tNone\tNone\n")
            else:
                line = f"{r[0]}\t{r[1]}"
                line += f"\t{results[r]['calc_dG']}\t{results[r]['calc_err']}"
                line += f"\t{results[r]['exp_dG']}\t{results[r]['exp_err']}"
                line += f"\t{results[r]['ref_dG']}\t{results[r]['ref_err']}\n"
                f.write(line)


@click.command
@click.option(
    '--scope_key',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    default="scoped-key.dat",
    help="Path to a serialized ScopedKey",
)
@click.option(
    '--output_file',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    default="results.dat",
    help="File location where the results TSV will be written.",
)
@click.option(
    '--reference_data',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    default="full_results_mnsol_2_0_0.csv",
    help="Reference data for analysis.",
)
@click.option(
    '--user_id',
    type=str,
    required=False,
    default=None,
)
@click.option(
    '--user_key',
    type=str,
    required=False,
    default=None,
)
def run(
    scope_key: pathlib.Path,
    output_file: pathlib.Path,
    reference_data: pathlib.Path,
    user_id: Optional[str],
    user_key: Optional[str],
):
    """
    Gather transformation results.

    Parameters
    ----------
    scope_key : pathlib.Path
      A path to a serialized ScopeKey
    output_file : pathlib.Path
      File location where the results TSV will be written.
    reference_data : pathlib.Path
      Reference data for analysis.
    user_id : Optional[str]
      A string for a user ID, if undefined will
      fetch from the environment variable ALCHEMISCALE_ID.
    user_key: Optional[str]
      A string for the user key, if underfined will
      fetch from the environment variable ALCHEMISCALE_KEY.
    """
    # Get the alchemiscale bits
    if user_id is None:
        user_id = os.environ['ALCHEMISCALE_ID']
    if user_key is None:
        user_key = os.environ['ALCHEMISCALE_KEY']
    asc = AlchemiscaleClient(
        'https://api.alchemiscale.org',
        user_id,
        user_key
    )

    # Read in the ScopeKey
    with open(scope_key, 'r') as f:
        network_sk = f.read()

    # Create a dictionary of the reference results
    benchmark_data = {}
    with open(reference_data, newline="") as csvfile:
        reader = csv.reader(csvfile, delimiter=",", quotechar="|")
        header = next(reader)

        def _get_quantity(var):
            if var == '':
                return None
            else:
                ret = float(var) * unit.kilojoule_per_mole
                return ret.to('kilocalorie_per_mole').m

        for row in reader:
            solute = row[5]
            solvent = row[4]
            exp_dG = _get_quantity(row[8])
            exp_err = _get_quantity(row[9])
            ref_dG = _get_quantity(row[10])
            ref_err = _get_quantity(row[11])

            benchmark_data[(solute, solvent)] = {
                'exp_dG': exp_dG,
                'exp_err': exp_err,
                'ref_dG': ref_dG,
                'ref_err': ref_err,
            }

    # Loop through each transformation and get the results
    results = {}  # The results container
    for transf_sk in asc.get_network_transformations(network_sk):
        transf = asc.get_transformation(transf_sk)
        dag_results = asc.get_transformation_results(
            transf_sk, return_protocoldagresults=True,
        )

        rdmol = transf.stateA.components['solute'].to_rdkit()
        name_solute = transf.stateA.components['solute'].to_rdkit().GetProp('smiles')
        name_solvent = transf.stateA.components['solvent'].solvent_molecule.to_rdkit().GetProp('smiles')
        name = (name_solute, name_solvent)
        print(name)

        dG, err = _process_dagresults(dag_results)

        def _get_kcal(var):
            if not isinstance(var, unit.Quantity):
                return None
            else:
                return var.to('kilocalorie_per_mole').m

        results[name] = {
            'calc_dG': _get_kcal(dG),
            'calc_err': _get_kcal(err),
            'exp_dG': benchmark_data[name]['exp_dG'],
            'exp_err': benchmark_data[name]['exp_err'],
            'ref_dG': benchmark_data[name]['ref_dG'],
            'ref_err': benchmark_data[name]['ref_err'],
        }

    # Write out all the results
    _write_results(results, output_file)


if __name__ == "__main__":
    run()

