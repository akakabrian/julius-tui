"""Hot-path benchmarks.

Stage 5 of the skill calls for baseline perf before optimizing. Times:
- One full render_line() pass over the visible viewport
- 100 sim_tick calls
- House-evolution sweep over N houses

Run:
    python -m tests.perf
"""

from __future__ import annotations

import time

from julius_tui import sim
from julius_tui.app import JuliusApp


def bench(label: str, fn, iters: int = 1) -> None:
    # Warm-up
    fn()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    dt = (time.perf_counter() - t0) / iters
    print(f"  {label:<40} {dt*1000:8.3f} ms/iter")


def main() -> None:
    print("julius-tui perf baseline")
    print("-" * 60)

    # 1. sim_tick without any buildings
    s = sim.Sim()
    bench("sim_tick (empty city)", s.sim_tick, iters=200)

    # 2. sim_tick with 50 houses + services
    s2 = sim.Sim(seed=7)
    # Scatter some buildings
    placed = 0
    for y in range(5, sim.MAP_H - 5, 3):
        for x in range(5, sim.MAP_W - 5, 3):
            if s2.do_tool(sim.BUILDING_ROAD, x, y) == sim.TOOLRESULT_OK:
                s2.place_house(x + 1, y)
                placed += 1
                if placed > 50:
                    break
        if placed > 50:
            break
    # Drop a few wells
    for x in range(10, 70, 12):
        s2.do_tool(sim.BUILDING_WELL, x, 20)
    print(f"  (city has {s2.building_count} buildings)")
    bench("sim_tick (50-house city)", s2.sim_tick, iters=200)

    # 3. render_line over the viewport
    async def bench_render():
        app = JuliusApp()
        async with app.run_test(size=(180, 60)) as pilot:
            await pilot.pause()
            mv = app.map_view

            def render_all() -> None:
                for y in range(60):
                    mv.render_line(y)

            bench("render_line × 60 rows", render_all, iters=50)

    import asyncio
    asyncio.run(bench_render())

    # 4. Service-coverage recompute (expensive monthly step)
    bench("recompute_service_coverage", s2._recompute_service_coverage,
          iters=50)


if __name__ == "__main__":
    main()
