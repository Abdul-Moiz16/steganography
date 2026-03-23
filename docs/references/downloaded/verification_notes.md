# Reference Verification Notes

## 2026-03-23

- `noda2006qim`: the previously downloaded `noda2006qim.pdf` was incorrect and has been removed. The corrected full text is now stored as `files/noda2006qim.xml`, resolved from DOI `10.1016/j.patrec.2005.09.008` via the Elsevier content API.
- `mereur2024deepfake`: verified against `files/mereur2024deepfake.pdf`.
  - Page 5 states that their experiments use three spatial embedding algorithms: `HILL`, `UNIWARD`, and `MiPOD`.
  - Page 6 clarifies that they used `S-UNIWARD`, `HILL`, and `MiPOD`, but due to space limits they only present results for the first two.
  - Page 4 defines steganalysis performance using the minimal total probability of error under equal prior (`P_E`), not AUC.
- Remaining unresolved full texts:
  - `chen_wornell2001`
  - `delong1988`
