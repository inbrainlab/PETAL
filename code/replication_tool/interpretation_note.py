"""Text shown after a comparison, to help read the size of the differences.

Used by evaluate_subject.py and compare_with_published.py so the wording lives in one place.
"""
import textwrap

WIDTH = 100

TAU_NOTE = (
    "Whether an error below 1% is small enough depends on the variability that the measurement already "
    "carries. For flortaucipir, the standard deviation of the test-retest change in cortical SUVR ranged "
    "from 1.5% to 5.0% across regions (Devous et al., 2018), and the longitudinal measurement error of a "
    "temporal meta-ROI referenced to the cerebellum without PVC, the configuration reproduced here, has "
    "been estimated at about 2-3% (Schwarz et al., 2021). The global and meta-temporal reproduction errors "
    "obtained for tau in the paper (0.45% and 0.25%) are therefore an order of magnitude below the variability between "
    "two scans of the same participant, so that regenerating the reference values from their documentation "
    "adds little to the uncertainty already inherent in the measurement."
)

TAU_PVC_WARNING = (
    "The same comparison shows where reproduction does matter: PVC-corrected values in small structures, "
    "with mean errors of 2-3% and individual errors of up to 25% (Section 4.2 of the paper), reach or "
    "exceed that variability. Differences in the PVC bilateral values of small structures (for example "
    "amygdala, entorhinal or parahippocampal cortex) should be read with this in mind."
)

GENERIC_NOTE = (
    "A single subject compares one value with one value: it shows whether your installation resembles "
    "ours, not agreement. Cohort-level agreement with the reference is reported in the paper."
)


def _wrap(text, indent="  "):
    return textwrap.fill(text, width=WIDTH, initial_indent=indent, subsequent_indent=indent)


def print_note(data_type, pvc_written=False):
    """Print the interpretation note for `data_type` ('tau', 'fdg' or 'centiloid')."""
    print("\n" + "-" * WIDTH)
    print("HOW TO READ THESE DIFFERENCES")
    if data_type == "tau":
        print(_wrap(TAU_NOTE))
        if pvc_written:
            print("\nWARNING (PVC values)")
            print(_wrap(TAU_PVC_WARNING))
    else:
        print(_wrap(GENERIC_NOTE))
    print("-" * WIDTH)
