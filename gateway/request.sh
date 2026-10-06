#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'for i in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:8099/api/job?id=10efdaafea1e4a918a17b08f8c256f82"; echo; sleep 1; done'
