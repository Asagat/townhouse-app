// --- App.tsx ---

import { Refine } from "@refinedev/core";
import dataProvider from "@refinedev/simple-rest";
import routerBindings, { NavigateToResource } from "@refinedev/react-router-v6";
import {
    BrowserRouter,
    Routes,
    Route,
    Outlet,
} from "react-router-dom";
import { ConfigProvider } from "antd";
import ruRU from "antd/locale/ru_RU";
import "dayjs/locale/ru";
import "antd/dist/reset.css";
import { allResources } from "./config/menu";
import { Sidebar } from "./components/layout/Sidebar";
import { GenericList } from "./pages/GenericList";

const App = () => {
    return (
        <ConfigProvider locale={ruRU}>
            <BrowserRouter>
                <Refine
                    dataProvider={dataProvider("/api")}
                    routerProvider={routerBindings}
                    resources={allResources.map((r) => ({
                        name: r.key,
                        list: `/${r.key}`,
                    }))}
                >
                    <Routes>
                        <Route
                            element={
                                <div style={{ display: "flex", minHeight: "100vh" }}>
                                    <Sidebar />
                                    <div
                                        style={{
                                            flex: 1,
                                            padding: "40px",
                                            background: "#f0f2f5",
                                        }}
                                    >
                                        <Outlet />
                                    </div>
                                </div>
                            }
                        >
                            <Route
                                index
                                element={<NavigateToResource resource="owners" />}
                            />
                            {allResources.map((r) => (
                                <Route
                                    key={r.key}
                                    path={`/${r.key}`}
                                    element={<GenericList resourceName={r.key} />}
                                />
                            ))}
                        </Route>
                    </Routes>
                </Refine>
            </BrowserRouter>
        </ConfigProvider>
    );
};

export default App;
