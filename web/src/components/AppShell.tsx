import { Layout, Menu } from "antd";
import { Link, Outlet, useLocation } from "react-router-dom";

const { Sider, Content, Header } = Layout;

export default function AppShell() {
  const location = useLocation();
  // "/sessions/sess-xxx" -> "sessions"; "/" -> "sessions"
  const selectedKey = location.pathname.split("/")[1] || "sessions";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider collapsible>
        <div
          style={{
            color: "white",
            padding: 16,
            fontWeight: 700,
            fontSize: 16,
          }}
        >
          AgentLabX
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            { key: "sessions", label: <Link to="/sessions">Sessions</Link> },
            { key: "plugins", label: <Link to="/plugins">Plugins</Link> },
            { key: "settings", label: <Link to="/settings">Settings</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", padding: "0 24px" }}>
          <h1 style={{ margin: 0, fontSize: 18 }}>AgentLabX</h1>
        </Header>
        <Content style={{ padding: 24, background: "#f5f5f5" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
