# lecroyutils

[![pypi](https://badgen.net/pypi/v/lecroyutils/)](https://pypi.org/project/lecroyutils/)

Library to communicate and parse .trc files with/from LeCroy oscilloscopes.

This library is based on previous work:
* File src/lecroyutils/data.py on [lecroyparser](https://github.com/bennomeier/leCroyParser)
* File src/lecroyutils/control.py on [LecroyScope_python_snippet](https://github.com/ethz-pes/LecroyScope_python_snippet)

## Features
* remote control LeCroy oscilloscopes over vxi11
    * does not require additional drivers (no visa)
    * controlling trigger settings
    * accessing statistics
    * downloading screenshots
    * view and donwload waveform data
* parse LeCroy .trc waveform data
    * support for sequence mode
    * x and y units

## Installation

lecroyutils is available in the Python Package Index (PyPi). It may be installed with pip:

```bash
> pip install lecroyutils
```

## Usage

```python
from lecroyutils.data import LecroyScopeData

# Parse a local .trc file
data = LecroyScopeData.parse_file('C2_00000_Lecroy.trc')

from lecroyutils.control import LecroyScope, TriggerMode, TriggerType

# Connect to a scope over vxi11
scope = LecroyScope('127.0.0.1')
scope.trigger_type = TriggerType.edge
scope.trigger_source = 'C1'
scope.acquire(force=True)
data = scope.waveform('C1')

scope.save_waveform('C1', 'C1_00000_Lecroy.trc')
```

## Related
* [lecroyparser](https://github.com/bennomeier/leCroyParser)
* [LecroyScope_python_snippet](https://github.com/ethz-pes/LecroyScope_python_snippet)
* [lecroydso](https://github.com/TeledyneLeCroy/lecroydso)
* [python-vxi11](https://github.com/python-ivi/python-vxi11)

## License
lecroyutils is licensed under the [MIT](LICENSE) license.

## Notice
We are not affiliated, associated, authorized, endorsed by, or in any way officially connected with Teledyne LeCroy, or any of its subsidiaries or its affiliates. The official Teledyne LeCroy github profile can be found at https://github.com/TeledyneLeCroy.
