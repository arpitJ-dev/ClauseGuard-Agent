# Dataset Notice

ClauseGuard's bundled perturbation benchmark is a selected 11-contract subset of
the artifacts published with **Better Call CLAUSE: A Discrepancy Benchmark for
Auditing LLMs Legal Reasoning Capabilities**. The subset preserves upstream file
names and perturbation metadata so benchmark labels can be traced to the source
artifact.

## Upstream Sources

- CLAUSE project and dataset: <https://github.com/clause-legal/clause-legal.github.io>
- CLAUSE paper: <https://aclanthology.org/2026.findings-eacl.305/>
- Contract Understanding Atticus Dataset (CUAD): <https://github.com/TheAtticusProject/cuad>
- ContractNLI project: <https://stanfordnlp.github.io/contract-nli/>

The CLAUSE paper describes a corpus of more than 7,500 perturbed agreements
derived from CUAD and ContractNLI across ten discrepancy categories. ClauseGuard
does not bundle that complete corpus. The files under `data/` contain 11 benchmark
cases and 31 perturbation records selected for deterministic regression testing.

## Licensing and Attribution

ClauseGuard's MIT license applies to the software in this repository. It does not
relicense the contract exhibits, upstream annotations, or CLAUSE-generated
perturbations. CUAD is distributed under Creative Commons Attribution 4.0; consult
the CLAUSE repository and paper for the terms and notices applicable to its
generated artifacts before redistributing the dataset separately.

When using the bundled benchmark in research or published evaluation, cite the
CLAUSE and CUAD works and identify ClauseGuard's data as a selected regression
subset rather than the complete upstream benchmark.

```bibtex
@inproceedings{choudhury-etal-2026-better,
  title = {Better Call {CLAUSE}: A Discrepancy Benchmark for Auditing {LLM}s Legal Reasoning Capabilities},
  author = {Choudhury, Manan Roy and Chandramouli, Adithya and Anand, Mannan and Gupta, Vivek},
  booktitle = {Findings of the Association for Computational Linguistics: EACL 2026},
  year = {2026},
  pages = {5776--5818},
  doi = {10.18653/v1/2026.findings-eacl.305}
}

@article{hendrycks2021cuad,
  title = {{CUAD}: An Expert-Annotated {NLP} Dataset for Legal Contract Review},
  author = {Hendrycks, Dan and Burns, Collin and Chen, Anya and Ball, Spencer},
  journal = {Advances in Neural Information Processing Systems},
  year = {2021}
}
```
