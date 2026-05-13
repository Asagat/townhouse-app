import { Refine, useTable } from "@refinedev/core";
import dataProvider from "@refinedev/simple-rest";
import routerBindings, { NavigateToResource } from "@refinedev/react-router-v6";
import { BrowserRouter, Routes, Route, Outlet, Link } from "react-router-dom";

const GenericList = ({ resourceName }: { resourceName: string }) => {
    const { tableQuery } = useTable({ resource: resourceName });
    const data = tableQuery?.data?.data ?? [];

    if (tableQuery.isLoading)
        return (
            <div style={{ color: "#000", padding: "20px" }}>
                Загрузка из БД...
            </div>
        );

    return (
        <div
            style={{
                background: "#fff",
                padding: "30px",
                borderRadius: "12px",
                width: "100%",
                boxSizing: "border-box",
            }}
        >
            <h1 style={{ color: "#1f1f1f", marginBottom: "20px" }}>
                СПИСОК: {resourceName.toUpperCase()} (V2)
            </h1>
            <table
                style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    color: "#000",
                }}
            >
                <thead>
                    <tr
                        style={{
                            textAlign: "left",
                            borderBottom: "2px solid #f0f0f0",
                        }}
                    >
                        <th style={{ padding: "12px" }}>ID</th>
                        <th style={{ padding: "12px" }}>ФИО</th>
                        <th style={{ padding: "12px" }}>Телефон</th>
                    </tr>
                </thead>
                <tbody>
                    {data.map((item: any) => (
                        <tr
                            key={item.id}
                            style={{ borderBottom: "1px solid #eee" }}
                        >
                            <td style={{ padding: "12px" }}>{item.id}</td>
                            <td style={{ padding: "12px" }}>
                                {item.fio || item.name || item.full_name || "—"}
                            </td>
                            <td style={{ padding: "12px" }}>
                                {item.phone || "—"}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

const App = () => {
    const myModels = ["owners", "houses", "flats", "payments"];
    return (
        <BrowserRouter>
            <Refine
                dataProvider={dataProvider("/api")}
                routerProvider={routerBindings}
                resources={myModels.map((m) => ({ name: m, list: `/${m}` }))}
            >
                <Routes>
                    <Route
                        element={
                            <div
                                style={{
                                    display: "flex",
                                    minHeight: "100vh",
                                    background: "#f0f2f5",
                                }}
                            >
                                <div
                                    style={{
                                        width: "240px",
                                        background: "#001529",
                                        color: "#fff",
                                        padding: "20px",
                                    }}
                                >
                                    <h2>Townhouse</h2>
                                    <nav
                                        style={{
                                            display: "flex",
                                            flexDirection: "column",
                                            gap: "10px",
                                        }}
                                    >
                                        {myModels.map((m) => (
                                            <Link
                                                key={m}
                                                to={`/${m}`}
                                                style={{
                                                    color: "#fff",
                                                    textDecoration: "none",
                                                }}
                                            >
                                                📂 {m}
                                            </Link>
                                        ))}
                                    </nav>
                                </div>
                                <div style={{ flex: 1, padding: "40px" }}>
                                    <Outlet />
                                </div>
                            </div>
                        }
                    >
                        <Route
                            index
                            element={<NavigateToResource resource="owners" />}
                        />
                        {myModels.map((m) => (
                            <Route
                                key={m}
                                path={`/${m}`}
                                element={<GenericList resourceName={m} />}
                            />
                        ))}
                    </Route>
                </Routes>
            </Refine>
        </BrowserRouter>
    );
};

export default App;
