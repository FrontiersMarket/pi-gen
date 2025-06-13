#!/usr/bin/env python3

test_line = "SDUSDFPSFD  Super awesome test data file for testing\n"
# Each line is about 53 bytes, so we need about 20000 lines to get 1MB
with open('test-data/cool-test.txt', 'w') as f:
    for _ in range(20000):
        f.write(test_line)
