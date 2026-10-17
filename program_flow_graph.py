"""Program structure graph for the PACR iteration reports (HTML via pyvis, PNG via matplotlib)."""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from pyvis.network import Network  # noqa: E402

# (node, iteration in which it is introduced)
NODES: list[tuple[str, int]] = [
    ("config.load_config", 1), ("config.SystemConfig", 1), ("config.load_credentials", 1),
    ("config.write_config_atomic", 1), ("config.Inventory", 1),
    ("models.MovementRequest", 1), ("clock.Clock", 1),
    ("sdn_api.SdnMsg", 1), ("sdn_api.encode_request", 1), ("sdn_api.FrameParser", 1),
    ("sdn_api.decode_frame", 1), ("sdn_api.decode_feedback", 1),
    ("serial_interface.SerialInterface", 2), ("sdn_sim.SdnSim", 2), ("sdn_sim.SdnRecorder", 2),
    ("sdn_sim.compare", 2), ("sdn_api.SdnApi", 2),
    ("controller.CurtainController", 3), ("controller.MotorState", 3), ("controller.Operation", 3),
    ("curtain_control.CurtainControl", 4), ("curtain_control.StateRepository", 4),
    ("scheduler.CurtainScheduler", 4), ("data_sources.DataSources", 4),
    ("main.parse_args", 5), ("main.create_app", 5), ("main.routes", 5), ("static.client", 5),
    ("config.WeatherConfig", 6), ("data_sources.NwsWeatherProvider", 6),
    ("data_sources.HttpWeatherProvider", 6), ("weather_schema.PointResponse", 6),
    ("weather_schema.StationResponse", 6), ("weather_schema.ObservationResponse", 6),
    ("NWS API", 6),
]

EDGES: list[tuple[str, str]] = [
    ("config.load_config", "config.SystemConfig"),
    ("config.SystemConfig", "config.Inventory"),
    ("config.load_credentials", "config.SystemConfig"),
    ("config.write_config_atomic", "config.SystemConfig"),
    ("models.MovementRequest", "sdn_api.encode_request"),
    ("sdn_api.encode_request", "sdn_api.SdnMsg"),
    ("sdn_api.FrameParser", "sdn_api.decode_frame"),
    ("sdn_api.decode_frame", "sdn_api.decode_feedback"),
    ("clock.Clock", "sdn_api.FrameParser"),
    ("sdn_api.SdnApi", "sdn_api.encode_request"),
    ("sdn_api.SdnApi", "sdn_api.FrameParser"),
    ("sdn_api.SdnApi", "sdn_api.decode_feedback"),
    ("sdn_api.SdnApi", "serial_interface.SerialInterface"),
    ("sdn_api.SdnApi", "sdn_sim.SdnSim"),
    ("sdn_api.SdnApi", "sdn_sim.SdnRecorder"),
    ("sdn_sim.SdnRecorder", "sdn_sim.compare"),
    ("clock.Clock", "sdn_sim.SdnSim"),
    ("config.Inventory", "sdn_sim.SdnSim"),
    ("controller.CurtainController", "sdn_api.SdnApi"),
    ("controller.CurtainController", "models.MovementRequest"),
    ("controller.CurtainController", "controller.MotorState"),
    ("controller.CurtainController", "controller.Operation"),
    ("config.Inventory", "controller.CurtainController"),
    ("curtain_control.CurtainControl", "controller.CurtainController"),
    ("curtain_control.CurtainControl", "curtain_control.StateRepository"),
    ("curtain_control.CurtainControl", "config.Inventory"),
    ("scheduler.CurtainScheduler", "curtain_control.CurtainControl"),
    ("scheduler.CurtainScheduler", "data_sources.DataSources"),
    ("main.parse_args", "main.create_app"),
    ("main.create_app", "config.load_config"),
    ("main.create_app", "config.load_credentials"),
    ("main.create_app", "sdn_api.SdnApi"),
    ("main.create_app", "controller.CurtainController"),
    ("main.create_app", "curtain_control.CurtainControl"),
    ("main.create_app", "scheduler.CurtainScheduler"),
    ("main.create_app", "main.routes"),
    ("main.routes", "curtain_control.CurtainControl"),
    ("main.routes", "config.write_config_atomic"),
    ("static.client", "main.routes"),
    ("main.create_app", "data_sources.DataSources"),
    ("data_sources.DataSources", "config.WeatherConfig"),
    ("data_sources.DataSources", "data_sources.NwsWeatherProvider"),
    ("data_sources.DataSources", "data_sources.HttpWeatherProvider"),
    ("data_sources.NwsWeatherProvider", "weather_schema.PointResponse"),
    ("data_sources.NwsWeatherProvider", "weather_schema.StationResponse"),
    ("data_sources.NwsWeatherProvider", "weather_schema.ObservationResponse"),
    ("data_sources.NwsWeatherProvider", "NWS API"),
    ("data_sources.NwsWeatherProvider", "clock.Clock"),
]


def program_flow_graph(html_graph_path: str = "program_flow_graph.html",
                       png_graph_path: str | None = None, max_iteration: int = 99) -> str:
    nodes = [n for n, it in NODES if it <= max_iteration]
    present = set(nodes)
    edges = [{"source": s, "target": t} for s, t in EDGES if s in present and t in present]
    graph = nx.node_link_graph(
        {"directed": True, "multigraph": False, "nodes": [{"id": n} for n in nodes], "edges": edges},
        edges="edges",
    )
    if png_graph_path:
        plt.figure(figsize=(16, 10))
        pos = nx.spring_layout(graph, seed=7, k=1.2)
        nx.draw(graph, pos, with_labels=True, node_size=2200, node_color="lightblue",
                font_size=7, font_weight="bold", arrows=True)
        plt.title(f"CurtainControl program structure after iteration {max_iteration}")
        plt.savefig(png_graph_path, dpi=90, bbox_inches="tight")
        plt.close()
    net = Network(notebook=False, cdn_resources="remote", directed=True, height="1000px",
                  width="100%", bgcolor="#222222", font_color="white", select_menu=True)
    net.from_nx(graph)
    net.write_html(html_graph_path)
    return html_graph_path


if __name__ == "__main__":
    it = int(sys.argv[1]) if len(sys.argv) > 1 else 99
    program_flow_graph(f"docs/graphs/iteration_{it}.html", f"docs/graphs/iteration_{it}.png", it)
