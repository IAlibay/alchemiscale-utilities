## How to run some ASFE simulations with Pontibus on Alchemiscale.

### 1. Create an AlchemicalNetwork

First you need to create a :class:`AlchemicalNetwork` which defines all the transformations
you want to run. In this case, each transformation is an absolute hydration free energy using
Pontibus' :class:`ASFEProtocol`. This is done in the `gen_network.py` script.

Here we take in an SDF with pre-charged molecules (`mnsol_am1bccelf10.sdf`) and 
the reference results from the Sage benchmarks (`full_results_mnsol_2_0_0.csv`).
With these we create a set of :class:`openfe.ChemicalSystems` (see :meth:`get_chemical_systems`).

For each of these we create a Transformation which goes from a state wtih the solute to one without
(see :meth:`get_transformation`). In doing so, we assign a set of simulation settings for the
Transformation Protocol (see :meth:`get_nonwater_settings`). Please see some of the comments in the
script to see how you can tune a few things.

### 2. Submit the AlchemicalNetwork

Next we submit the :class:`AlchemicalNetwork` to Alchemiscale and action out the tasks.

#### Setting your Alchemiscale user id / key

To submit to Alchemiscale, you must have either a user ID or key.

Here we expect your id/key to either be set as the environment variables `ALCHEMISCALE_ID`
and `ALCHEMISCALE_KEY` or to be passed via the ``--user_id`` and ``--user_key`` flags.

#### Setting your Scope

Every experiment needs a Scope to keep track of what you are doing.

The scope is defined in three parts: `<organization>`, `<campaign>`, `<project>`.

For benchmarking, we often set the campaign to be an indicator of a given stack version,
and the project to be the experiment, i.e. `<openfe>`, `<openfe_v1.2>`, `<minisolv_elf10>`.

Remember that you are not allowed certain types of characters in your scope, such as; `-`.

You can read more about the scope here: https://docs.alchemiscale.org/en/latest/user_guide.html#choosing-a-scope

#### Setting the number of repeats

On Alchemiscale we set each task to run a single DAG of a Protocol. However we can
have multiple repeats (in order to get better estimates of the sampling error) by
submitting the same task multiple times.

To do this, we can use the ``--repeats`` flag.


#### Example

Here is an example call for the script w/ 3 repeats per Transformation on the openfe scope:

```bash
python submit.py --network_filename network.json --org_scope "openfe" --scope_name_campaign "ofe_v1_2" --scope_name_project "minisolv_oechemelf10" --repeats 3
```

### 3. Monitoring your simulation

You can monitor your simulation by querying the Alchemiscale network status.

To help with this, we provide the ``monitor.py` script.

You can call it like this:

```bash
python monitor.py --scope_key scoped-key.dat
```

Here ``scoped-key.dat`` is the serialized ScopedKey that we generated when we
called ``submit.py``.

As per the ``submit.py`` script, you can also manually pass your user ID/key.

#### Restarting simulations

In some cases you might find that some jobs have failed and gone to ``error`` mode.
Due to the heterogenous nature of Alchemiscale, this can often happen due to hardware
failures or other random issues. It is usually advised to try to restart the simulations
a few times to see what happens.

You can use the ``--restart`` flag to achieve this:

```bash
python monitor.py --scope_key scoped-key.dat --restart
```

This will put all errored tasks back into the queue and attempt to run them again.


### 4. Getting results.

Finally, once your simulations are complete, you can gather the free energy results.

This can be done with ``gather.py`` in the following manner:

```bash
python gather.py --scope_key scoped-key.dat --reference_data full_results_mnsol_2_0_0.csv --output_file results.dat
```

This scripts scans through all the Transformations and gathers ProtocolDAGResults.
It then takes the dG estimates for all the repeats and returns an average and a standard deviation.

It also extracts information from the reference data to store in the results TSV alongside the new calculated results.

Note 1: if you only run a single repeat, it may be useful to directly use the MBAR error. This
is not done here, but this script could be easily modified to do this.

Note 2: the ProtocolDAGResults contain other types of information, such as the MBAR overlap matrix
and the forward & reverse energy series. Again, this data is not obtained with this script but
it could be modified to retrieve this.
