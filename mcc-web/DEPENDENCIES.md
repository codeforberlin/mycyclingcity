# Project Dependencies

This document provides a comprehensive overview of all Python dependencies used in the mcc-web project, including their versions and licenses.

## Direct Dependencies

| Library Name | Version | License | Notes |
|--------------|---------|---------|-------|
| Django | 5.2.9 | BSD-3-Clause | Web framework |
| requests | 2.32.5 | Apache-2.0 | HTTP library |
| gunicorn | 23.0.0 | MIT | WSGI HTTP Server |
| gpxpy | 1.6.2 | Apache-2.0 | GPX file parser |
| pillow | 12.0.0 | PIL | Image processing library |
| python-decouple | 3.8 | MIT | Environment variable management |
| python-dotenv | 1.0.0 | BSD-3-Clause | .env file support |
| pytest | 8.0.0 | MIT | Testing framework |
| pytest-django | 4.8.0 | BSD-3-Clause | Django plugin for pytest |
| factory-boy | 3.3.0 | MIT | Test data generation |

## License Summary

### Permissive Licenses (No Restrictions)

The following dependencies use permissive licenses that allow commercial use, modification, and distribution:

- **MIT License** (5 packages):
  - gunicorn
  - python-decouple
  - pytest
  - factory-boy

- **Apache-2.0** (2 packages):
  - requests
  - gpxpy

- **BSD-3-Clause** (3 packages):
  - Django
  - python-dotenv
  - pytest-django

- **PIL License** (1 package):
  - pillow (HPND-like license, permissive)

## License Compliance

### Restrictive Licenses

**No restrictive licenses (GPL, AGPL, LGPL) detected.**

All dependencies in this project use permissive licenses that are compatible with commercial use and do not impose copyleft restrictions. The project is free to use, modify, and distribute without license compliance concerns.

### License Compatibility

All dependencies are compatible with each other and can be used together in commercial and open-source projects without restrictions.

## Additional Information

- **SBOM Format**: CycloneDX JSON (version 1.5)
- **SBOM Location**: `sbom.json` in the project root
- **Last Updated**: 2025-01-27
- **Source**: Generated from `requirements.txt`

## Notes

- The PIL license used by Pillow is a permissive license similar to HPND (Historical Permission Notice and Disclaimer).
- All listed dependencies are direct dependencies specified in `requirements.txt`.
- Transitive dependencies (dependencies of dependencies) are not listed here but may be included in the SBOM if generated with dependency resolution tools.
