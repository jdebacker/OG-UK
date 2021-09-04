import multiprocessing
from distributed import Client
import json
import time
import os
from openfisca_core.model_api import Reform
from oguk.calibrate import Calibration
from ogcore import output_tables as ot
from ogcore import output_plots as op
from ogcore.execute import runner
from ogcore.utils import safe_read_pickle

# Set start year and last year
START_YEAR = 2018
from ogcore.parameters import Specifications


def main():
    # Define parameters to use for multiprocessing
    client = Client()
    num_workers = min(multiprocessing.cpu_count(), 7)
    print("Number of workers = ", num_workers)

    # Directories to save data
    CUR_DIR = os.path.dirname(os.path.realpath(__file__))
    base_dir = os.path.join(CUR_DIR, "OG-UK-Example", "OUTPUT_BASELINE")
    reform_dir = os.path.join(CUR_DIR, "OG-UK-Example", "OUTPUT_REFORM")

    """
    ------------------------------------------------------------------------
    Run baseline policy
    ------------------------------------------------------------------------
    """
    # Set up baseline parameterization
    p = Specifications(
        baseline=True,
        num_workers=num_workers,
        baseline_dir=base_dir,
        output_base=base_dir,
    )
    # Update parameters for baseline from default json file
    p.update_specifications(
        json.load(
            open(
                os.path.join(
                    CUR_DIR, "..", "oguk", "oguk_default_parameters.json"
                )
            )
        )
    )
    # specify tax function form and start year
    p.update_specifications(
        {
            "tax_func_type": "DEP",
            "age_specific": False,
            "start_year": START_YEAR,
            "alpha_T": [5e-3],
            "alpha_G": [5e-3],
        }
    )
    # Estimate baseline tax functions from OpenFisca-UK
    c = Calibration(p, estimate_tax_functions=True, client=client)
    # update tax function parameters in Specifications Object
    d = c.get_dict()
    updated_params = {
        "etr_params": d["etr_params"],
        "mtrx_params": d["mtrx_params"],
        "mtry_params": d["mtry_params"],
        "mean_income_data": d["mean_income_data"],
        "frac_tax_payroll": d["frac_tax_payroll"],
    }
    p.update_specifications(updated_params)
    # Run model
    start_time = time.time()
    runner(p, time_path=True, client=client)
    print("run time = ", time.time() - start_time)

    """
    ------------------------------------------------------------------------
    Run reform policy
    ------------------------------------------------------------------------
    """
    # Create a parametric reform for OpenFisca-UK
    def lower_pa(parameters):
        parameters.tax.income_tax.allowances.personal_allowance.amount.update(
            period="2018", value=10000
        )
        return parameters

    class lower_personal_tax_allowance(Reform):
        def apply(self):
            self.modify_parameters(modifier_function=lower_pa)

    reform = lower_personal_tax_allowance

    # create new Specifications object for reform simulation
    p2 = Specifications(
        baseline=False,
        num_workers=num_workers,
        baseline_dir=base_dir,
        output_base=reform_dir,
    )
    # Update parameters for baseline from default json file
    p2.update_specifications(
        json.load(
            open(
                os.path.join(
                    CUR_DIR, "..", "oguk", "oguk_default_parameters.json"
                )
            )
        )
    )
    # specify tax function form and start year
    p2.update_specifications(
        {
            "tax_func_type": "DEP",
            "age_specific": False,
            "start_year": START_YEAR,
            "alpha_T": [5e-3],
            "alpha_G": [5e-3],
        }
    )
    # Estimate reform tax functions from OpenFisca-UK, passing Reform
    # class object
    c2 = Calibration(
        p2, iit_reform=reform, estimate_tax_functions=True, client=client
    )
    # update tax function parameters in Specifications Object
    d2 = c2.get_dict()
    updated_params2 = {
        "etr_params": d2["etr_params"],
        "mtrx_params": d2["mtrx_params"],
        "mtry_params": d2["mtry_params"],
        "mean_income_data": d2["mean_income_data"],
        "frac_tax_payroll": d2["frac_tax_payroll"],
    }
    p2.update_specifications(updated_params2)
    # Run model
    start_time = time.time()
    runner(p2, time_path=True, client=client)
    print("run time = ", time.time() - start_time)

    """
    ------------------------------------------------------------------------
    Save some results of simulations
    ------------------------------------------------------------------------
    """
    base_tpi = safe_read_pickle(os.path.join(base_dir, "TPI", "TPI_vars.pkl"))
    base_params = safe_read_pickle(os.path.join(base_dir, "model_params.pkl"))
    reform_tpi = safe_read_pickle(
        os.path.join(reform_dir, "TPI", "TPI_vars.pkl")
    )
    reform_params = safe_read_pickle(
        os.path.join(reform_dir, "model_params.pkl")
    )
    ans = ot.macro_table(
        base_tpi,
        base_params,
        reform_tpi=reform_tpi,
        reform_params=reform_params,
        var_list=["Y", "C", "K", "L", "r", "w"],
        output_type="pct_diff",
        num_years=10,
        start_year=base_params.start_year,
    )

    # create plots of output
    op.plot_all(
        base_dir, reform_dir, os.path.join(CUR_DIR, "OG-UK_example_plots")
    )

    print("Percentage changes in aggregates:", ans)
    # save percentage change output to csv file
    ans.to_csv("oguk_example_output.csv")
    client.close()


if __name__ == "__main__":
    # execute only if run as a script

    parser = ArgumentParser(
        description="A script to run the main OG-UK routine on a reform."
    )
    parser.add_argument(
        "reform",
        default="small_ubi_reform.ubi_reform",
        help="The Python reform object to use as a reform (if `reform` is defined in `reform_file.py`, then use `reform_file.reform`)",
    )
    args = parser.parse_args()

    reform_path = args.reform.split(".")
    python_module, object_name = ".".join(reform_path[:-1]), reform_path[-1]
    reform = getattr(__import__(python_module), object_name)
    main(reform)
