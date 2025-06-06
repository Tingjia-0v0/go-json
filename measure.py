import os
import subprocess
import sys

# Dependencies:
# 1. Install graphviz: sudo apt install graphviz
# 2. Install FlameGraph to where you want: git clone https://github.com/brendangregg/FlameGraph.git 
# 3. Install go-torch: go install github.com/uber/go-torch@latest

# usage:
# python3 measure.py <workloads> <flamegraph_dir>
# find the flamegraph in analyze_<workloads> directory

# Setup configuration
workloads = sys.argv[1] if len(sys.argv) > 1 else "withoutsleep" # withoutsleep, withsleep
flamegraph_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "FlameGraph")
# Setup possible CPUsets, gomaxprocs, and parallelisms you want to test
CPUsets = {
    '8p': '0,2,4,6,8,10,12,14',
}
possible_gomaxprocs   = [8] 
possible_parallelisms = [1] # see RunParallel function in go's testing package
benchiters = {'withsleep': 50000, 'withoutsleep': 500000}
benchiter = benchiters[workloads]

# Setup environment variables
os.environ['PATH'] = os.environ['PATH'] + ':' + flamegraph_dir
os.environ['PATH'] = os.environ['PATH'] + ':' + subprocess.check_output(['go', 'env', 'GOPATH']).decode().strip() + '/bin'

# Setup result directory
Result_dir = f'analyze_{workloads}'
if os.path.exists(Result_dir):
    for file in os.listdir(Result_dir):
        os.remove(os.path.join(Result_dir, file))
os.makedirs(Result_dir, exist_ok=True)

def measure_cpu_utilization(cpuset):
    totals = []
    idles = []
    cpuset = [int(cpu) for cpu in cpuset.split(',')]
    with open('/proc/stat', 'r') as f:
        for line in f:
            if line.startswith('cpu'):
                cpu_name = line.split()[0]
                if cpu_name == 'cpu':  # Skip aggregate line
                    continue
                cpu_id = int(cpu_name[3:])  # Extract number from cpuN
                if cpu_id in cpuset:
                    cputimes = [int(i) for i in line.split()[1:]]
                    totals.append(sum(cputimes))
                    idles.append(cputimes[3] + cputimes[4])
    assert len(totals) == len(cpuset)
    assert len(idles) == len(cpuset)
    return totals, idles


for (cpuname, cpuset) in CPUsets.items():
    # Change to benchmarks directory
    os.chdir('benchmarks')

    latencies = {}
    throughputs = {}
    cpu_utilizations = {}

    for possible_parallelism in possible_parallelisms:
        latencies[possible_parallelism] = {}
        throughputs[possible_parallelism] = {}
        cpu_utilizations[possible_parallelism] = {}
        os.environ['parallelism'] = str(possible_parallelism)
        for gomaxprocs in possible_gomaxprocs:
            os.environ['GOMAXPROCS'] = str(gomaxprocs)
            # Get initial CPU stats for the specified CPUs
            initial_totals, initial_idles = measure_cpu_utilization(cpuset)

            subprocess.run([
                'taskset', '-c', cpuset,
                'go', 'test',
                f'-bench=Benchmark_Decode_MixStruct_Parallel_Unmarshal_GoJson_{workloads}',
                # '-benchmem',
                f'-cpuprofile=../{Result_dir}/cpu.prof',
                '-benchtime=' + str(benchiter) + 'x'
            ], env=os.environ, stdout=open(f'../{Result_dir}/output.txt', 'w'))

            # Run the benchmark and measure CPU stats after
            final_totals, final_idles = measure_cpu_utilization(cpuset)
            # Calculate utilization percentage for each CPU
            cpu_usage_percentage = {}
            for i in range(len(initial_totals)):
                delta_total = final_totals[i] - initial_totals[i]
                delta_idle = final_idles[i] - initial_idles[i]
                cpu_usage_percentage[i] = 100.0 * (delta_total - delta_idle) / delta_total

            cpu_utilizations[possible_parallelism][gomaxprocs] = sum(cpu_usage_percentage.values()) / len(cpu_usage_percentage)

            subprocess.run([
                'go-torch',
                f'../{Result_dir}/cpu.prof',
                '-f', f'../{Result_dir}/{cpuname}_{gomaxprocs}_{possible_parallelism}.svg'
            ], env=os.environ)
            

            with open(f'../{Result_dir}/output.txt', 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if 'ns/op' in line:
                        latencies[possible_parallelism][gomaxprocs] = float(line.split()[1])
                        throughputs[possible_parallelism][gomaxprocs] = float(line.split()[3])

print(latencies)
print(throughputs)
print(cpu_utilizations)