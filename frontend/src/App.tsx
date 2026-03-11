import { Refine, useTable } from "@refinedev/core";
import dataProvider from "@refinedev/simple-rest";
import routerBindings, { NavigateToResource } from "@refinedev/react-router-v6";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";

// Компонент таблицы
const OwnersList = () => {
  // useTable автоматически делает запрос к {API}/owners
  const { tableQuery } = useTable({
    resource: "owners",
  });

  const owners = tableQuery?.data?.data ?? [];

  if (tableQuery.isLoading) return <div>Загрузка владельцев...</div>;

  return (
    <div style={{ background: "#fff", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
      <h1 style={{ marginBottom: "20px" }}>Список владельцев</h1>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #f0f0f0" }}>
            <th style={{ padding: "12px" }}>ID</th>
            <th style={{ padding: "12px" }}>ФИО</th>
            <th style={{ padding: "12px" }}>Телефон</th>
          </tr>
        </thead>
        <tbody>
          {owners.map((owner: any) => (
            <tr key={owner.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td style={{ padding: "12px" }}>{owner.id}</td>
              <td style={{ padding: "12px", fontWeight: "bold" }}>{owner.fio || owner.name}</td>
              <td style={{ padding: "12px" }}>{owner.phone || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {owners.length === 0 && <p style={{ padding: "20px", textAlign: "center" }}>Данных пока нет.</p>}
    </div>
  );
};

const App = () => {
  return (
    <BrowserRouter>
      <Refine
        dataProvider={dataProvider("http://localhost:8000")}
        routerProvider={routerBindings}
        resources={[{ name: "owners", list: "/owners" }]}
        options={{ telemetry: "off" }}
      >
        <Routes>
          <Route element={
            <div style={{ display: "flex", minHeight: "100vh", fontFamily: "sans-serif" }}>
              <div style={{ width: "200px", background: "#001529", color: "#fff", padding: "20px" }}>
                <h3 style={{ color: "#1890ff" }}>Townhouse</h3>
                <nav>
                  <a href="/owners" style={{ color: "#fff", textDecoration: "none" }}>👥 Собственники</a>
                </nav>
              </div>
              <div style={{ flex: 1, padding: "40px", background: "#f0f2f5" }}>
                <Outlet />
              </div>
            </div>
          }>
            <Route index element={<NavigateToResource resource="owners" />} />
            <Route path="/owners" element={<OwnersList />} />
          </Route>
        </Routes>
      </Refine>
    </BrowserRouter>
  );
};

export default App;
