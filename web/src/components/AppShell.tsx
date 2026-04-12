import { Layout, Menu } from "antd";
import {
  AppstoreOutlined,
  ExperimentOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Link, Outlet, useLocation } from "react-router-dom";

const { Sider, Content, Header } = Layout;

export default function AppShell() {
  const location = useLocation();
  // "/sessions/sess-xxx" -> "sessions"; "/" -> "sessions"
  const selectedKey = location.pathname.split("/")[1] || "sessions";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        width={220}
        style={{ borderRight: "1px solid rgba(255,255,255,0.04)" }}
      >
        <div
          style={{
            color: "#fafafa",
            padding: "18px 20px",
            fontWeight: 600,
            fontSize: 16,
            letterSpacing: "-0.01em",
          }}
        >
          AgentLabX
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          style={{ borderInlineEnd: "none", paddingInline: 8 }}
          items={[
            {
              key: "sessions",
              icon: <ExperimentOutlined />,
              label: <Link to="/sessions">Sessions</Link>,
            },
            {
              key: "plugins",
              icon: <AppstoreOutlined />,
              label: <Link to="/plugins">Plugins</Link>,
            },
            {
              key: "settings",
              icon: <SettingOutlined />,
              label: <Link to="/settings">Settings</Link>,
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#ffffff",
            padding: "0 24px",
            borderBottom: "1px solid #efefef",
            display: "flex",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontSize: 15,
              fontWeight: 500,
              color: "#525252",
              letterSpacing: "-0.01em",
            }}
          >
            AgentLabX
          </span>
        </Header>
        <Content
          style={{
            padding: "32px 40px",
            background: "#fafafa",
          }}
        >
          <div style={{ maxWidth: 1280, margin: "0 auto" }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
