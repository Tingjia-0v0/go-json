import os
import subprocess
import sys

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

# Setup configuration
workloads = sys.argv[1] if len(sys.argv) > 1 else "withoutsleep" # withoutsleep, withsleep
flamegraph_dir = sys.argv[2] if len(sys.argv) > 2 else "/users/Tingjia/project/FlameGraph"
# Setup possible CPUsets
CPUsets = {
    '8p': '0,2,4,6,8,10,12,14',
}

possible_gomaxprocs   = [8]
possible_parallelisms = [1]

benchiters = {'withsleep': 50000, 'withoutsleep': 500000, 'randomsleep': 50000}

os.environ['PATH'] = os.environ['PATH'] + ':' + flamegraph_dir
os.environ['PATH'] = os.environ['PATH'] + ':' + subprocess.check_output(['go', 'env', 'GOPATH']).decode().strip() + '/bin'

Result_dir = f'analyze_{workloads}'
benchiter = benchiters[workloads]

# Create flamegraphs directory
# Clear and recreate flamegraphs directory
if os.path.exists(Result_dir):
    for file in os.listdir(Result_dir):
        os.remove(os.path.join(Result_dir, file))
os.makedirs(Result_dir, exist_ok=True)

max_throughput = 0
max_latency = 0

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
                        max_latency = max(max_latency, latencies[possible_parallelism][gomaxprocs])
                        max_throughput = max(max_throughput, throughputs[possible_parallelism][gomaxprocs])

print(latencies)
print(throughputs)
print(cpu_utilizations)