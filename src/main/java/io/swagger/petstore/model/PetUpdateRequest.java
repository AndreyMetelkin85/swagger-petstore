package io.swagger.petstore.model;

import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import java.util.UUID;

@XmlRootElement(name = "PetUpdateRequest")
public class PetUpdateRequest extends PetCreateRequest {
    private UUID id;
    private Integer version;

    @XmlElement(name = "id")
    public UUID getId() {
        return id;
    }

    public void setId(final UUID id) {
        this.id = id;
    }

    @XmlElement(name = "version")
    public Integer getVersion() {
        return version;
    }

    public void setVersion(final Integer version) {
        this.version = version;
    }
}
